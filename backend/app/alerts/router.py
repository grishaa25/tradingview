"""Inbound webhooks — TradingView Pro alerts enter the platform here.

Set the alert's webhook URL in TradingView to:
    https://<backend-host>/alerts/webhooks/tradingview?secret=<WEBHOOK_SECRET>
and put a JSON message body in the alert, e.g.:
    {"ticker": "{{ticker}}", "side": "buy", "price": {{close}},
     "time": "{{timenow}}", "note": "daily RSI>60 setup"}

Events land in public.webhook_events; a worker normalizes them into
signals/alert_deliveries so TradingView alerts flow through the same
Telegram + journal pipeline as native scanner signals.
"""

import hmac
import json

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import text

from app.alerts.channels.telegram import send_message
from app.core.config import get_settings
from app.core.deps import DbSession

router = APIRouter()


@router.post("/webhooks/tradingview")
async def tradingview_webhook(request: Request, db: DbSession, secret: str = "") -> dict:
    settings = get_settings()
    if not settings.webhook_secret or not hmac.compare_digest(secret, settings.webhook_secret):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bad webhook secret")

    # Stored raw first so a parsing bug never loses an alert; a worker (or the
    # dispatcher) normalizes processed=false rows into alert deliveries.
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        payload = {"raw": (await request.body()).decode(errors="replace")}

    event_id = (
        await db.execute(
            text(
                "INSERT INTO webhook_events (source, payload) "
                "VALUES ('tradingview', CAST(:payload AS jsonb)) RETURNING id"
            ),
            {"payload": json.dumps(payload)},
        )
    ).scalar_one()
    await db.commit()

    # Forward to Telegram immediately; the stored row is the safety net if
    # formatting/sending fails.
    forwarded = False
    try:
        forwarded = await send_message(format_tradingview_alert(payload))
        if forwarded:
            await db.execute(
                text("UPDATE webhook_events SET processed = true WHERE id = :id"),
                {"id": event_id},
            )
            await db.commit()
    except Exception as exc:  # noqa: BLE001 — never bounce TradingView's webhook
        await db.execute(
            text("UPDATE webhook_events SET error = :e WHERE id = :id"),
            {"e": str(exc), "id": event_id},
        )
        await db.commit()

    return {"stored": True, "event_id": event_id, "telegram_forwarded": forwarded}


def format_tradingview_alert(payload: dict) -> str:
    """Render a TradingView alert payload for Telegram.

    Recognizes the recommended message format
    {"ticker","side","price","time","note"}; anything else is passed
    through raw so no alert is ever silently dropped.
    """
    if isinstance(payload, dict) and "ticker" in payload:
        side = str(payload.get("side", "alert")).upper()
        emoji = {"BUY": "🟢", "SELL": "🔴"}.get(side, "📈")
        parts = [f"{emoji} <b>TradingView: {side} {payload['ticker']}</b>"]
        if payload.get("price") is not None:
            parts.append(f"price {payload['price']}")
        if payload.get("note"):
            parts.append(str(payload["note"]))
        return " | ".join(parts)
    return f"📈 <b>TradingView alert</b> | {json.dumps(payload)[:500]}"

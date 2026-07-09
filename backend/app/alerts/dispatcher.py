"""Signal → alert channel fanout.

format_signal_message renders the ARCHITECTURE §3.2 style:
  🟢 BUY RELIANCE | daily_rsi_bullish 64.2 > 60 ✓ | ...
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.channels.telegram import send_message


def format_signal_message(ticker: str, side: str, conditions: list[dict]) -> str:
    emoji = "🟢" if side == "buy" else "🔴"
    parts = [f"{emoji} <b>{side.upper()} {ticker}</b>"]
    for c in conditions:
        mark = "✓" if c.get("passed") else "✗"
        parts.append(f"{c['id']} {c.get('left')} {c['operator']} {c.get('right')} {mark}")
    return " | ".join(parts)


async def dispatch_signals(session: AsyncSession, fired: list[dict]) -> int:
    """Send fired signals to Telegram and stamp delivered_at. Returns sent count."""
    sent = 0
    for sig in fired:
        ok = await send_message(
            format_signal_message(sig["ticker"], sig["side"], sig["conditions"])
        )
        if ok:
            await session.execute(
                text("UPDATE signals SET delivered_at = now() WHERE id = :id"),
                {"id": sig["signal_id"]},
            )
            sent += 1
    await session.commit()
    return sent

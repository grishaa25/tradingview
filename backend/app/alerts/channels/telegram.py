"""Telegram delivery channel — the Phase-1 alert path (free, instant)."""

import httpx

from app.core.config import get_settings

API = "https://api.telegram.org/bot{token}/sendMessage"


async def send_message(text: str, chat_id: str | None = None) -> bool:
    settings = get_settings()
    if not settings.telegram_bot_token:
        return False
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            API.format(token=settings.telegram_bot_token),
            json={
                "chat_id": chat_id or settings.telegram_chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
        )
    return resp.status_code == 200

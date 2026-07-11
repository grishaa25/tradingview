"""AI assistant: conversation persistence, market-context injection, budget guard.

Model calls go through LiteLLM so any provider works by exporting its key
(GROQ_API_KEY for the free tier, or OPENAI_API_KEY / ANTHROPIC_API_KEY / ...)
and setting AI_MODEL. Spend is metered per message into ai_messages.cost and
capped by AI_MONTHLY_BUDGET_USD across the calendar month.
"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import context as ctx
from app.core.config import get_settings
from app.marketdata import service as marketdata
from app.marketdata.fno_seed import FNO_TICKERS, TICKER_ALIASES

log = logging.getLogger(__name__)

HISTORY_LIMIT = 12  # prior messages replayed to the model per turn


class BudgetExceeded(Exception):
    pass


async def month_spend(session: AsyncSession, user_id: str) -> float:
    row = await session.execute(
        text(
            "SELECT coalesce(sum(m.cost), 0) FROM ai_messages m "
            "JOIN ai_conversations c ON c.id = m.conv_id "
            "WHERE c.user_id = :uid AND m.created_at >= date_trunc('month', now())"
        ),
        {"uid": user_id},
    )
    return float(row.scalar_one())


async def _get_or_create_conversation(
    session: AsyncSession, user_id: str, conv_id: int | None, first_message: str
) -> int:
    if conv_id is not None:
        row = await session.execute(
            text("SELECT id FROM ai_conversations WHERE id = :id AND user_id = :uid"),
            {"id": conv_id, "uid": user_id},
        )
        if row.first() is None:
            raise LookupError(f"conversation {conv_id} not found")
        return conv_id
    row = await session.execute(
        text(
            "INSERT INTO ai_conversations (user_id, title) VALUES (:uid, :title) "
            "RETURNING id"
        ),
        {"uid": user_id, "title": first_message[:80]},
    )
    return row.scalar_one()


async def _load_history(session: AsyncSession, conv_id: int) -> list[dict]:
    result = await session.execute(
        text(
            "SELECT role, content FROM ("
            "  SELECT role, content, id FROM ai_messages "
            "  WHERE conv_id = :c AND role IN ('user','assistant') "
            "  ORDER BY id DESC LIMIT :n"
            ") t ORDER BY id"
        ),
        {"c": conv_id, "n": HISTORY_LIMIT},
    )
    return [dict(r) for r in result.mappings()]


async def _recent_signals(session: AsyncSession, limit: int = 10) -> list[dict]:
    result = await session.execute(
        text(
            "SELECT sig.ts, sig.side, s.ticker, sc.name AS scan "
            "FROM signals sig "
            "JOIN symbols s ON s.id = sig.symbol_id "
            "JOIN scans sc ON sc.id = sig.scan_id "
            "ORDER BY sig.ts DESC LIMIT :n"
        ),
        {"n": limit},
    )
    return [dict(r) for r in result.mappings()]


async def _store_message(
    session: AsyncSession,
    conv_id: int,
    role: str,
    content: str,
    tokens: int | None = None,
    cost: float | None = None,
) -> None:
    await session.execute(
        text(
            "INSERT INTO ai_messages (conv_id, role, content, tokens, cost) "
            "VALUES (:c, :r, :m, :t, :cost)"
        ),
        {"c": conv_id, "r": role, "m": content, "t": tokens, "cost": cost},
    )


async def chat(
    session: AsyncSession, user_id: str, message: str, conv_id: int | None = None
) -> dict:
    settings = get_settings()

    spent = await month_spend(session, user_id)
    if spent >= settings.ai_monthly_budget_usd:
        raise BudgetExceeded(
            f"monthly AI budget exhausted (${spent:.2f} of "
            f"${settings.ai_monthly_budget_usd:.2f}); raise AI_MONTHLY_BUDGET_USD"
        )

    conv_id = await _get_or_create_conversation(session, user_id, conv_id, message)
    history = await _load_history(session, conv_id)

    tickers = ctx.extract_tickers(message, set(FNO_TICKERS), TICKER_ALIASES)
    quotes = await marketdata.get_quotes(session, tickers, "1D") if tickers else []
    signals = await _recent_signals(session)
    market_context = ctx.format_market_context(quotes, signals)

    # Imported lazily: litellm pulls in its whole provider registry on import.
    import litellm

    response = await litellm.acompletion(
        model=settings.ai_model,
        messages=ctx.build_messages(message, history, market_context),
        max_tokens=800,
        temperature=0.3,
    )
    reply = response.choices[0].message.content or ""
    tokens = getattr(response.usage, "total_tokens", None)
    try:
        cost = litellm.completion_cost(completion_response=response)
    except Exception:  # noqa: BLE001 — unknown models simply meter as $0
        cost = 0.0

    await _store_message(session, conv_id, "user", message)
    await _store_message(session, conv_id, "assistant", reply, tokens, cost)
    await session.commit()

    return {
        "conv_id": conv_id,
        "reply": reply,
        "tokens": tokens,
        "cost": round(cost or 0.0, 6),
        "month_spend": round(spent + (cost or 0.0), 4),
        "context_tickers": tickers,
    }


async def list_conversations(session: AsyncSession, user_id: str) -> list[dict]:
    result = await session.execute(
        text(
            "SELECT id, title, created_at FROM ai_conversations "
            "WHERE user_id = :uid ORDER BY created_at DESC LIMIT 50"
        ),
        {"uid": user_id},
    )
    return [dict(r) for r in result.mappings()]


async def list_messages(session: AsyncSession, user_id: str, conv_id: int) -> list[dict]:
    result = await session.execute(
        text(
            "SELECT m.id, m.role, m.content, m.created_at FROM ai_messages m "
            "JOIN ai_conversations c ON c.id = m.conv_id "
            "WHERE m.conv_id = :c AND c.user_id = :uid ORDER BY m.id"
        ),
        {"c": conv_id, "uid": user_id},
    )
    return [dict(r) for r in result.mappings()]

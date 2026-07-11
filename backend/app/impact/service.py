"""Nifty Impact Engine — decompose today's index move into per-stock points.

Index-point contribution of stock i ≈ index_prev_close · w_i · Δ%_i, with
weights normalized so the decomposition always sums to the weighted-average
move even when the static weight snapshot has drifted. Constituent moves come
from our own candles (free Yahoo/bhavcopy path); the ^NSEI index level itself
comes live from Yahoo since NSE indices aren't in the equity candle universe.
"""

import logging

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.impact.weights_seed import NIFTY50_WEIGHTS
from app.marketdata import service as marketdata
from app.marketdata.ingest import yahoo

log = logging.getLogger(__name__)

NSEI_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI"  # ^NSEI


def compute_contributions(
    index_prev_close: float,
    constituents: list[dict],  # [{ticker, weight, change_pct}]
) -> list[dict]:
    """Pure math: per-stock index-point impact, sorted most positive first.

    Stocks with missing change_pct are passed through with impact None so the
    UI can show them as "no data" instead of silently dropping them.
    """
    total_w = sum(c["weight"] for c in constituents) or 1.0
    out = []
    for c in constituents:
        chg = c.get("change_pct")
        impact = (
            round(index_prev_close * (c["weight"] / total_w) * chg / 100, 2)
            if chg is not None
            else None
        )
        out.append({**c, "impact_points": impact})
    out.sort(key=lambda x: x["impact_points"] if x["impact_points"] is not None else 0,
             reverse=True)
    return out


async def fetch_index_quote() -> dict:
    """Live ^NSEI daily candles → {level, prev_close, change_pct}."""
    async with httpx.AsyncClient(headers=yahoo.HEADERS, timeout=20) as client:
        resp = await client.get(NSEI_URL, params={"interval": "1d", "range": "10d"})
        resp.raise_for_status()
        bars = yahoo.parse_chart(resp.json())
    if len(bars) < 2:
        raise ValueError("Yahoo returned fewer than 2 daily bars for ^NSEI")
    level, prev = bars[-1]["c"], bars[-2]["c"]
    return {
        "level": level,
        "prev_close": prev,
        "change_pct": marketdata.compute_change_pct(prev, level),
        "asof": bars[-1]["ts"].isoformat(),
    }


async def get_nifty_impact(session: AsyncSession) -> dict:
    index = await fetch_index_quote()
    quotes = await marketdata.get_quotes(session, list(NIFTY50_WEIGHTS.keys()), "1D")
    by_ticker = {q["ticker"]: q for q in quotes}

    constituents = [
        {
            "ticker": t,
            "weight": w,
            "close": by_ticker.get(t, {}).get("close"),
            "change_pct": by_ticker.get(t, {}).get("change_pct"),
        }
        for t, w in NIFTY50_WEIGHTS.items()
    ]
    contributions = compute_contributions(index["prev_close"], constituents)
    explained = round(
        sum(c["impact_points"] for c in contributions if c["impact_points"] is not None), 2
    )
    missing = [c["ticker"] for c in contributions if c["change_pct"] is None]
    return {
        "index": index,
        "index_points_change": round(index["level"] - index["prev_close"], 2),
        "explained_points": explained,
        "contributions": contributions,
        "missing_data": missing,
    }

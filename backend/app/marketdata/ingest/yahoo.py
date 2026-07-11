"""Yahoo Finance chart API — the zero-credential data path.

Free, keyless, and covers NSE symbols as `{TICKER}.NS` with both daily and
60-minute candles (hourly intraday history goes back ~730 days). This is what
makes the dual-timeframe rules.json scan runnable before any broker account
exists. Not tick-accurate and ~15 min delayed intraday — fine for scanning,
and the bhavcopy overwrites daily candles with official numbers at EOD.

Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/{symbol}
"""

import asyncio
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json",
}

# platform timeframe → (yahoo interval, default range)
TF_MAP = {
    "1D": ("1d", "2y"),
    "60": ("60m", "6mo"),
}


def yahoo_symbol(ticker: str, exchange: str = "NSE") -> str:
    suffix = {"NSE": ".NS", "BSE": ".BO"}.get(exchange, ".NS")
    return f"{ticker}{suffix}"


def parse_chart(payload: dict) -> list[dict]:
    """Pure parser: v8 chart JSON → [{ts, o, h, l, c, v}] (skips null bars)."""
    try:
        result = payload["chart"]["result"][0]
        timestamps = result.get("timestamp") or []
        quote = result["indicators"]["quote"][0]
    except (KeyError, IndexError, TypeError):
        return []

    rows: list[dict] = []
    opens, highs = quote.get("open") or [], quote.get("high") or []
    lows, closes = quote.get("low") or [], quote.get("close") or []
    volumes = quote.get("volume") or []
    for i, ts in enumerate(timestamps):
        o, h = _at(opens, i), _at(highs, i)
        lo, c = _at(lows, i), _at(closes, i)
        if None in (o, h, lo, c):
            continue  # yahoo pads illiquid/halted bars with nulls
        rows.append(
            {
                "ts": datetime.fromtimestamp(ts, tz=timezone.utc),
                "o": round(o, 2),
                "h": round(h, 2),
                "l": round(lo, 2),
                "c": round(c, 2),
                "v": int(_at(volumes, i) or 0),
            }
        )
    return rows


def _at(lst: list, i: int):
    return lst[i] if i < len(lst) else None


async def fetch_candles(
    ticker: str, tf: str, client: httpx.AsyncClient, range_: str | None = None
) -> list[dict]:
    interval, default_range = TF_MAP[tf]
    resp = await client.get(
        CHART_URL.format(symbol=yahoo_symbol(ticker)),
        params={"interval": interval, "range": range_ or default_range},
    )
    resp.raise_for_status()
    return parse_chart(resp.json())


async def upsert_candle_rows(
    session: AsyncSession, symbol_id: int, tf: str, rows: list[dict]
) -> int:
    if not rows:
        return 0
    import json

    result = await session.execute(
        text(
            "INSERT INTO candles (symbol_id, tf, ts, o, h, l, c, v) "
            "SELECT :sid, :tf, x.ts::timestamptz, x.o, x.h, x.l, x.c, x.v "
            "FROM jsonb_to_recordset(CAST(:rows AS jsonb)) "
            "AS x(ts text, o numeric, h numeric, l numeric, c numeric, v bigint) "
            "ON CONFLICT (symbol_id, tf, ts) DO UPDATE "
            "SET o = excluded.o, h = excluded.h, l = excluded.l, "
            "    c = excluded.c, v = excluded.v"
        ),
        {
            "sid": symbol_id,
            "tf": tf,
            "rows": json.dumps(
                [{**r, "ts": r["ts"].isoformat()} for r in rows]
            ),
        },
    )
    return result.rowcount or 0


async def backfill(
    session: AsyncSession,
    symbols: list[dict],  # [{id, ticker}]
    timeframes: list[str] = ("1D", "60"),
    delay_s: float = 0.6,
) -> dict:
    """Backfill candles for many symbols. Polite: sequential with a delay.

    ~190 symbols × 2 timeframes at 0.6 s spacing ≈ 4 minutes. Idempotent.
    """
    stats = {"symbols": len(symbols), "upserted": 0, "failed": []}
    async with httpx.AsyncClient(headers=HEADERS, timeout=30) as client:
        for sym in symbols:
            for tf in timeframes:
                try:
                    rows = await fetch_candles(sym["ticker"], tf, client)
                    stats["upserted"] += await upsert_candle_rows(
                        session, sym["id"], tf, rows
                    )
                except Exception as exc:  # noqa: BLE001 — one bad symbol must not stop the rest
                    log.warning("backfill %s %s failed: %s", sym["ticker"], tf, exc)
                    stats["failed"].append(f"{sym['ticker']}:{tf}")
                await asyncio.sleep(delay_s)
    await session.commit()
    return stats

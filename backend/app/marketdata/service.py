"""Market-data queries shared by the API and the scanner runner."""

import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def list_symbols(
    session: AsyncSession, fno: bool | None = None, search: str | None = None
) -> list[dict]:
    clauses, params = [], {}
    if fno is not None:
        clauses.append("fno_flag = :fno")
        params["fno"] = fno
    if search:
        clauses.append("(ticker ILIKE :q OR name ILIKE :q)")
        params["q"] = f"%{search}%"
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    result = await session.execute(
        text(
            "SELECT id, ticker, exchange, name, sector, fno_flag, lot_size "
            f"FROM symbols {where} ORDER BY ticker LIMIT 500"
        ),
        params,
    )
    return [dict(r) for r in result.mappings()]


async def get_candles(
    session: AsyncSession, ticker: str, tf: str, limit: int = 500
) -> list[dict]:
    result = await session.execute(
        text(
            "SELECT c.ts, c.o, c.h, c.l, c.c, c.v, c.oi "
            "FROM candles c JOIN symbols s ON s.id = c.symbol_id "
            "WHERE s.exchange = 'NSE' AND s.ticker = :ticker AND c.tf = :tf "
            "ORDER BY c.ts DESC LIMIT :limit"
        ),
        {"ticker": ticker.upper(), "tf": tf, "limit": limit},
    )
    rows = [dict(r) for r in result.mappings()]
    rows.reverse()  # oldest first for charting
    return rows


async def load_candles_bulk(
    session: AsyncSession, symbol_ids: list[int], timeframes: list[str], bars: int = 300
) -> dict[int, dict[str, pd.DataFrame]]:
    """symbol_id → timeframe → OHLCV DataFrame (o,h,l,c,v columns, oldest first).

    One query per timeframe for the whole universe (ARCHITECTURE §3.2 bulk load).
    """
    out: dict[int, dict[str, pd.DataFrame]] = {sid: {} for sid in symbol_ids}
    for tf in timeframes:
        result = await session.execute(
            text(
                "SELECT symbol_id, ts, o, h, l, c, v FROM ("
                "  SELECT symbol_id, ts, o, h, l, c, v, "
                "         row_number() OVER (PARTITION BY symbol_id ORDER BY ts DESC) rn "
                "  FROM candles WHERE tf = :tf AND symbol_id = ANY(:ids)"
                ") t WHERE rn <= :bars ORDER BY symbol_id, ts"
            ),
            {"tf": tf, "ids": symbol_ids, "bars": bars},
        )
        rows = result.mappings().all()
        if not rows:
            continue
        df = pd.DataFrame(rows)
        for col in ("o", "h", "l", "c", "v"):
            df[col] = pd.to_numeric(df[col])
        for sid, group in df.groupby("symbol_id"):
            out[int(sid)][tf] = group.reset_index(drop=True)
    return out


def compute_change_pct(prev_close: float | None, last_close: float | None) -> float | None:
    """Pure helper: % change from prev_close to last_close, guarding zero/None."""
    if prev_close is None or last_close is None or prev_close == 0:
        return None
    return round((last_close - prev_close) / prev_close * 100, 2)


async def get_quotes(session: AsyncSession, tickers: list[str], tf: str = "1D") -> list[dict]:
    """Latest two candles per ticker → {ticker, ts, close, prev_close, change_pct}.

    Used by the watchlist dashboard: one query for many symbols instead of
    N round-trips.
    """
    result = await session.execute(
        text(
            "SELECT ticker, ts, c FROM ("
            "  SELECT s.ticker, c.ts, c.c, "
            "         row_number() OVER (PARTITION BY s.id ORDER BY c.ts DESC) rn "
            "  FROM candles c JOIN symbols s ON s.id = c.symbol_id "
            "  WHERE s.exchange = 'NSE' AND s.ticker = ANY(:tickers) AND c.tf = :tf "
            ") t WHERE rn <= 2 ORDER BY ticker, ts DESC"
        ),
        {"tickers": [t.upper() for t in tickers], "tf": tf},
    )
    by_ticker: dict[str, list[dict]] = {}
    for row in result.mappings():
        by_ticker.setdefault(row["ticker"], []).append(dict(row))

    quotes = []
    for ticker in tickers:
        rows = by_ticker.get(ticker.upper())
        if not rows:
            quotes.append({"ticker": ticker.upper(), "ts": None, "close": None,
                            "prev_close": None, "change_pct": None, "has_data": False})
            continue
        last = float(rows[0]["c"])
        prev = float(rows[1]["c"]) if len(rows) > 1 else None
        quotes.append({
            "ticker": ticker.upper(),
            "ts": rows[0]["ts"],
            "close": last,
            "prev_close": prev,
            "change_pct": compute_change_pct(prev, last),
            "has_data": True,
        })
    return quotes


async def resolve_universe(session: AsyncSession, universe: dict) -> list[dict]:
    """rules.json universe block → [{id, ticker}] (full F&O or top-liquid-N)."""
    mode = universe.get("mode", "full")
    if mode == "top_liquid_50" or universe.get("liquidity_filter", {}).get("enabled"):
        top_n = universe.get("liquidity_filter", {}).get("top_n", 50)
        result = await session.execute(
            text(
                "SELECT s.id, s.ticker FROM symbols s "
                "JOIN liquidity_stats l ON l.symbol_id = s.id "
                "WHERE s.fno_flag AND l.asof_date = ("
                "  SELECT max(asof_date) FROM liquidity_stats) "
                "ORDER BY l.rank LIMIT :n"
            ),
            {"n": top_n},
        )
    else:
        result = await session.execute(
            text("SELECT id, ticker FROM symbols WHERE fno_flag ORDER BY ticker")
        )
    return [dict(r) for r in result.mappings()]

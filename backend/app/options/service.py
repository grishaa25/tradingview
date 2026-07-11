"""Option-chain orchestration: fetch → parse → analytics → snapshot persist."""

import json
import logging
import time
from datetime import date, datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.options import analytics, nse_chain

log = logging.getLogger(__name__)

# Small in-process TTL cache so a watch-the-chain user doesn't hammer NSE.
CACHE_TTL_S = 180
_cache: dict[str, tuple[float, dict, list[dict]]] = {}


async def _fetch_parsed(symbol: str) -> tuple[dict, list[dict]]:
    key = symbol.upper()
    hit = _cache.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1], hit[2]
    payload = await nse_chain.fetch_chain(key)
    meta, rows = nse_chain.parse_chain(payload)
    _cache[key] = (time.monotonic() + CACHE_TTL_S, meta, rows)
    return meta, rows


def pick_expiry(expiries: list[str], requested: str | None) -> str | None:
    """Requested expiry if listed, else the nearest expiry from today on."""
    if requested and requested in expiries:
        return requested
    today = date.today().isoformat()
    upcoming = [e for e in expiries if e >= today]
    return upcoming[0] if upcoming else (expiries[-1] if expiries else None)


def merge_by_strike(rows: list[dict]) -> list[dict]:
    """Single-expiry rows → [{strike, ce: {...}|None, pe: {...}|None}] sorted."""
    by_strike: dict[float, dict] = {}
    for r in rows:
        slot = by_strike.setdefault(r["strike"], {"strike": r["strike"], "ce": None, "pe": None})
        leg = {k: v for k, v in r.items() if k not in ("expiry", "strike", "opt_type")}
        slot["ce" if r["opt_type"] == "CE" else "pe"] = leg
    return sorted(by_strike.values(), key=lambda s: s["strike"])


async def get_chain(session: AsyncSession, symbol: str, expiry: str | None = None) -> dict:
    meta, all_rows = await _fetch_parsed(symbol)
    chosen = pick_expiry(meta["expiries"], expiry)
    rows = [r for r in all_rows if r["expiry"] == chosen]
    spot = meta["spot"]

    try:  # history is a bonus, never a failure mode for the live view
        await save_snapshot(session, symbol, rows)
    except Exception:  # noqa: BLE001
        log.warning("chain snapshot persist failed for %s", symbol, exc_info=True)

    return {
        "symbol": symbol.upper(),
        "spot": spot,
        "expiry": chosen,
        "expiries": meta["expiries"],
        "fetched_at": meta["fetched_at"],
        "analytics": analytics.summarize(rows, spot),
        "strikes": merge_by_strike(rows),
    }


async def _ensure_symbol(session: AsyncSession, ticker: str) -> int:
    """Indices like NIFTY aren't in the equity seed — create rows on demand."""
    row = await session.execute(
        text(
            "INSERT INTO symbols (ticker, exchange) VALUES (:t, 'NSE') "
            "ON CONFLICT (exchange, ticker) DO UPDATE SET ticker = excluded.ticker "
            "RETURNING id"
        ),
        {"t": ticker.upper()},
    )
    return row.scalar_one()


async def save_snapshot(session: AsyncSession, symbol: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    symbol_id = await _ensure_symbol(session, symbol)
    ts = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    result = await session.execute(
        text(
            "INSERT INTO chain_snapshots "
            "  (symbol_id, expiry, strike, opt_type, ts, ltp, oi, oi_chg, iv, volume, bid, ask) "
            "SELECT :sid, x.expiry::date, x.strike, x.opt_type, :ts, "
            "       x.ltp, x.oi, x.oi_chg, x.iv, x.volume, x.bid, x.ask "
            "FROM jsonb_to_recordset(CAST(:rows AS jsonb)) AS x("
            "  expiry text, strike numeric, opt_type text, ltp numeric, oi bigint, "
            "  oi_chg bigint, iv numeric, volume bigint, bid numeric, ask numeric) "
            "ON CONFLICT (symbol_id, expiry, strike, opt_type, ts) DO NOTHING"
        ),
        {"sid": symbol_id, "ts": ts, "rows": json.dumps(rows)},
    )
    await session.commit()
    return result.rowcount or 0

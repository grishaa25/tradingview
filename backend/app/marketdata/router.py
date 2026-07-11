from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app.core.deps import CurrentUser, DbSession
from app.marketdata import service
from app.marketdata.fno_seed import FNO_TICKERS
from app.marketdata.ingest import yahoo
from app.marketdata.ingest.bhavcopy import ingest_bhavcopy

router = APIRouter()


@router.get("/symbols")
async def list_symbols(
    db: DbSession,
    user: CurrentUser,
    fno: bool | None = None,
    search: str | None = None,
) -> list[dict]:
    return await service.list_symbols(db, fno=fno, search=search)


@router.get("/candles/{ticker}")
async def get_candles(
    ticker: str,
    db: DbSession,
    user: CurrentUser,
    tf: str = "1D",
    limit: int = 500,
) -> list[dict]:
    rows = await service.get_candles(db, ticker, tf, min(limit, 2000))
    if not rows:
        raise HTTPException(404, f"no {tf} candles for {ticker.upper()}")
    return rows


# ---------------------------------------------------------------------------
# Admin/bootstrap endpoints — run ingestion on demand instead of waiting for
# the scheduler. Single-user platform: any authenticated user may trigger.
# ---------------------------------------------------------------------------


@router.post("/admin/seed-universe")
async def seed_universe(db: DbSession, user: CurrentUser) -> dict:
    """Bootstrap the F&O universe from the static snapshot (idempotent)."""
    import json

    result = await db.execute(
        text(
            "INSERT INTO symbols (ticker, exchange, fno_flag) "
            "SELECT x.ticker, 'NSE', true "
            "FROM jsonb_to_recordset(CAST(:rows AS jsonb)) AS x(ticker text) "
            "ON CONFLICT (exchange, ticker) DO UPDATE SET fno_flag = true"
        ),
        {"rows": json.dumps([{"ticker": t} for t in FNO_TICKERS])},
    )
    await db.commit()
    return {"seeded": result.rowcount or 0}


@router.post("/admin/backfill")
async def backfill_yahoo(
    db: DbSession,
    user: CurrentUser,
    tickers: str | None = None,
    limit: int = 200,
) -> dict:
    """Backfill 1D + 60m candles from Yahoo Finance (free, keyless).

    `tickers`: optional comma-separated subset (e.g. "RELIANCE,TCS");
    otherwise the whole F&O universe up to `limit` symbols. ~190 symbols
    take ≈4 min; start with a subset to see data instantly.
    """
    if tickers:
        wanted = [t.strip().upper() for t in tickers.split(",") if t.strip()]
        result = await db.execute(
            text("SELECT id, ticker FROM symbols WHERE ticker = ANY(:t)"),
            {"t": wanted},
        )
    else:
        result = await db.execute(
            text("SELECT id, ticker FROM symbols WHERE fno_flag ORDER BY ticker LIMIT :n"),
            {"n": limit},
        )
    symbols = [dict(r) for r in result.mappings()]
    if not symbols:
        raise HTTPException(400, "no matching symbols — run /admin/seed-universe first")
    return await yahoo.backfill(db, symbols)


@router.post("/admin/ingest-eod")
async def ingest_eod(
    db: DbSession, user: CurrentUser, for_date: date | None = None
) -> dict:
    """Run the official NSE bhavcopy ingest for a date (default: today IST)."""
    ist_today = datetime.now(timezone(timedelta(hours=5, minutes=30))).date()
    try:
        count = await ingest_bhavcopy(db, for_date or ist_today)
    except Exception as exc:  # surface NSE fetch errors clearly
        raise HTTPException(502, f"bhavcopy fetch/ingest failed: {exc}") from exc
    return {"date": str(for_date or ist_today), "candles_upserted": count}

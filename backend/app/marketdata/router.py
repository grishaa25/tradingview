from fastapi import APIRouter, HTTPException

from app.core.deps import CurrentUser, DbSession
from app.marketdata import service

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

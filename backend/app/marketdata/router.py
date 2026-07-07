from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession

router = APIRouter()


@router.get("/symbols")
async def list_symbols(db: DbSession, user: CurrentUser, fno: bool = True) -> list[dict]:
    # Phase 1: query public.symbols (seeded from the NSE F&O list).
    raise NotImplementedError


@router.get("/candles/{ticker}")
async def get_candles(
    ticker: str, db: DbSession, user: CurrentUser, tf: str = "1D"
) -> list[dict]:
    # Phase 1: read from public.candles.
    raise NotImplementedError

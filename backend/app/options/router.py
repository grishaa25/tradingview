import httpx
from fastapi import APIRouter, HTTPException

from app.core.deps import CurrentUser, DbSession
from app.options import service

router = APIRouter()


@router.get("/chain/{symbol}")
async def get_chain(
    symbol: str, db: DbSession, user: CurrentUser, expiry: str | None = None
) -> dict:
    """Live option chain + analytics (PCR, max pain, OI walls, ATM IV).

    `symbol`: NIFTY / BANKNIFTY / FINNIFTY / MIDCPNIFTY or any F&O equity.
    `expiry`: optional YYYY-MM-DD; defaults to the nearest upcoming expiry.
    """
    try:
        return await service.get_chain(db, symbol, expiry)
    except httpx.HTTPError as exc:
        raise HTTPException(
            502,
            "NSE option-chain fetch failed (NSE throttles aggressively — "
            f"retry in a minute): {exc}",
        ) from exc

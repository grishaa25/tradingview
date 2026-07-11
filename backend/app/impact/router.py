import httpx
from fastapi import APIRouter, HTTPException

from app.core.deps import CurrentUser, DbSession
from app.impact import service

router = APIRouter()


@router.get("/nifty")
async def nifty_impact(db: DbSession, user: CurrentUser) -> dict:
    """Which stocks moved NIFTY today: per-constituent index-point impact."""
    try:
        return await service.get_nifty_impact(db)
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, f"index quote fetch failed: {exc}") from exc

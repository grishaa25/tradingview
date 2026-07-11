from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.deps import CurrentUser, DbSession
from app.ai import service

router = APIRouter()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conv_id: int | None = None


@router.post("/chat")
async def chat(body: ChatRequest, db: DbSession, user: CurrentUser) -> dict:
    """One assistant turn: persists both messages, injects market context."""
    try:
        return await service.chat(db, user["sub"], body.message, body.conv_id)
    except service.BudgetExceeded as exc:
        raise HTTPException(402, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — surface provider/key errors readably
        raise HTTPException(
            502,
            "LLM call failed — check AI_MODEL and that the matching provider "
            f"key (e.g. GROQ_API_KEY) is set in backend/.env: {exc}",
        ) from exc


@router.get("/conversations")
async def conversations(db: DbSession, user: CurrentUser) -> list[dict]:
    return await service.list_conversations(db, user["sub"])


@router.get("/conversations/{conv_id}/messages")
async def messages(conv_id: int, db: DbSession, user: CurrentUser) -> list[dict]:
    return await service.list_messages(db, user["sub"], conv_id)


@router.get("/usage")
async def usage(db: DbSession, user: CurrentUser) -> dict:
    settings = get_settings()
    spent = await service.month_spend(db, user["sub"])
    return {
        "month_spend_usd": round(spent, 4),
        "budget_usd": settings.ai_monthly_budget_usd,
        "model": settings.ai_model,
    }

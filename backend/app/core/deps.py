from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session

# Single-user app — no auth required.
_OWNER = {"sub": "00000000-0000-0000-0000-000000000001"}


async def get_current_user() -> dict:
    return _OWNER


CurrentUser = Annotated[dict, Depends(get_current_user)]
DbSession = Annotated[AsyncSession, Depends(get_session)]

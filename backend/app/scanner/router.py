from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession
from app.scanner.schema import Rules

router = APIRouter()


@router.post("/validate")
async def validate_rules(rules: Rules, user: CurrentUser) -> dict:
    """Parse a rules.json document against the scanner schema."""
    return {"valid": True, "indicators": [i.id for i in rules.indicators]}


@router.post("/{scan_id}/run")
async def run_scan(scan_id: int, db: DbSession, user: CurrentUser) -> dict:
    # Phase 1 week 4: manual scan pass end-to-end (ARCHITECTURE §12).
    raise NotImplementedError

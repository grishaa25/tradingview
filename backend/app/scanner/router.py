from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app.core.deps import CurrentUser, DbSession
from app.scanner.runner import run_scan_pass
from app.scanner.schema import Rules

router = APIRouter()


@router.post("/validate")
async def validate_rules(rules: Rules, user: CurrentUser) -> dict:
    """Parse a rules.json document against the scanner schema."""
    return {"valid": True, "indicators": [i.id for i in rules.indicators]}


@router.post("")
async def create_scan(rules: Rules, db: DbSession, user: CurrentUser) -> dict:
    import json

    scan_id = (
        await db.execute(
            text(
                "INSERT INTO scans (user_id, name, rules) "
                "VALUES (:uid, :name, CAST(:rules AS jsonb)) RETURNING id"
            ),
            {
                "uid": user["sub"],
                "name": rules.meta.get("name", "unnamed scan"),
                "rules": json.dumps(rules.model_dump(exclude_none=True)),
            },
        )
    ).scalar_one()
    await db.commit()
    return {"id": scan_id}


@router.post("/{scan_id}/run")
async def run_scan(scan_id: int, db: DbSession, user: CurrentUser) -> dict:
    owner = (
        await db.execute(
            text("SELECT user_id FROM scans WHERE id = :id"), {"id": scan_id}
        )
    ).scalar_one_or_none()
    if owner is None:
        raise HTTPException(404, "scan not found")
    if str(owner) != user["sub"]:
        raise HTTPException(403, "not your scan")
    return await run_scan_pass(db, scan_id)


@router.get("/{scan_id}/signals")
async def list_signals(
    scan_id: int, db: DbSession, user: CurrentUser, limit: int = 100
) -> list[dict]:
    result = await db.execute(
        text(
            "SELECT sig.id, sym.ticker, sig.side, sig.ts, sig.snapshot "
            "FROM signals sig "
            "JOIN scans sc ON sc.id = sig.scan_id AND sc.user_id = :uid "
            "JOIN symbols sym ON sym.id = sig.symbol_id "
            "WHERE sig.scan_id = :scan ORDER BY sig.ts DESC LIMIT :limit"
        ),
        {"uid": user["sub"], "scan": scan_id, "limit": min(limit, 500)},
    )
    return [dict(r) for r in result.mappings()]

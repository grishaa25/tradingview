"""Scan pass orchestration (ARCHITECTURE §3.2).

resolve universe → bulk-load candles → evaluate each symbol → re-arm state
machine → insert signals with full condition snapshots. Pure evaluation
lives in evaluator.py; this module owns the DB round-trips.
"""

import json
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.marketdata.service import load_candles_bulk, resolve_universe
from app.scanner.evaluator import PassContext, evaluate_symbol
from app.scanner.schema import Rules
from app.scanner.state import ARMED, transition

log = logging.getLogger(__name__)


def required_timeframes(rules: Rules) -> list[str]:
    tfs = {i.timeframe for i in rules.indicators}
    for side in rules.signals.values():
        for cond in side.conditions:
            for op in (cond.left, cond.right):
                if op is not None and op.timeframe:
                    tfs.add(op.timeframe)
    return sorted(tfs)


async def run_scan_pass(session: AsyncSession, scan_id: int) -> dict:
    """Run one full pass of a scan. Returns a summary with fired signals."""
    scan_row = (
        await session.execute(
            text("SELECT id, rules, enabled FROM scans WHERE id = :id"),
            {"id": scan_id},
        )
    ).mappings().first()
    if scan_row is None:
        raise LookupError(f"scan {scan_id} not found")
    rules = Rules.model_validate(
        scan_row["rules"] if isinstance(scan_row["rules"], dict)
        else json.loads(scan_row["rules"])
    )

    universe = await resolve_universe(session, rules.universe)
    tfs = required_timeframes(rules)
    candles = await load_candles_bulk(session, [s["id"] for s in universe], tfs)

    states = {
        (r["symbol_id"], r["side"]): r["state"]
        for r in (
            await session.execute(
                text("SELECT symbol_id, side, state FROM scan_state WHERE scan_id = :id"),
                {"id": scan_id},
            )
        ).mappings()
    }

    fired: list[dict] = []
    skipped = 0
    for sym in universe:
        sym_candles = candles.get(sym["id"], {})
        if any(tf not in sym_candles for tf in tfs):
            skipped += 1
            continue
        try:
            results = evaluate_symbol(PassContext(candles=sym_candles, rules=rules))
        except Exception:
            log.exception("evaluation failed for %s", sym["ticker"])
            skipped += 1
            continue

        for side, (conditions_true, snapshots) in results.items():
            prev = states.get((sym["id"], side), ARMED)
            new_state, should_fire = transition(prev, conditions_true)
            if new_state != prev:
                await session.execute(
                    text(
                        "INSERT INTO scan_state (scan_id, symbol_id, side, state, updated_at) "
                        "VALUES (:scan, :sym, :side, :state, now()) "
                        "ON CONFLICT (scan_id, symbol_id, side) "
                        "DO UPDATE SET state = excluded.state, updated_at = now()"
                    ),
                    {"scan": scan_id, "sym": sym["id"], "side": side, "state": new_state},
                )
            if should_fire:
                signal_id = (
                    await session.execute(
                        text(
                            "INSERT INTO signals (scan_id, symbol_id, side, ts, snapshot) "
                            "VALUES (:scan, :sym, :side, now(), CAST(:snap AS jsonb)) "
                            "RETURNING id"
                        ),
                        {
                            "scan": scan_id,
                            "sym": sym["id"],
                            "side": side,
                            "snap": json.dumps({"conditions": snapshots}),
                        },
                    )
                ).scalar_one()
                fired.append(
                    {
                        "signal_id": signal_id,
                        "ticker": sym["ticker"],
                        "side": side,
                        "conditions": snapshots,
                    }
                )

    await session.commit()
    return {
        "scan_id": scan_id,
        "universe_size": len(universe),
        "skipped_no_data": skipped,
        "signals": fired,
    }

"""Scheduled job bodies (ARCHITECTURE §6). All idempotent; all log to job_runs."""

import json
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text

from app.alerts.dispatcher import dispatch_signals
from app.core.db import SessionLocal
from app.marketdata.ingest.bhavcopy import ingest_bhavcopy
from app.marketdata.ingest.universe import refresh_universe
from app.scanner.runner import run_scan_pass

log = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


async def _log_run(job_name: str, coro) -> None:
    async with SessionLocal() as session:
        run_id = (
            await session.execute(
                text("INSERT INTO job_runs (job_name) VALUES (:n) RETURNING id"),
                {"n": job_name},
            )
        ).scalar_one()
        await session.commit()
        try:
            detail = await coro(session)
            status, detail_json = "ok", detail
        except Exception as exc:  # noqa: BLE001 — jobs must never kill the scheduler
            log.exception("job %s failed", job_name)
            status, detail_json = "error", {"error": str(exc)}
        await session.execute(
            text(
                "UPDATE job_runs SET finished_at = now(), status = :s, "
                "detail = CAST(:d AS jsonb) WHERE id = :id"
            ),
            {"s": status, "d": json.dumps(detail_json), "id": run_id},
        )
        await session.commit()


async def eod_bhavcopy() -> None:
    """18:30 IST: official EOD candles + F&O universe refresh."""

    async def body(session):
        today = datetime.now(IST).date()
        if await _is_holiday(session, today):
            return {"skipped": "holiday"}
        candles = await ingest_bhavcopy(session, today)
        lots = await refresh_universe(session)
        return {"candles_upserted": candles, "fno_symbols": lots}

    await _log_run("eod_bhavcopy", body)


async def hourly_scan_pass() -> None:
    """10:15..15:15 + 15:30 IST: run every enabled scan, dispatch alerts."""

    async def body(session):
        if await _is_holiday(session, datetime.now(IST).date()):
            return {"skipped": "holiday"}
        scan_ids = [
            r[0]
            for r in await session.execute(text("SELECT id FROM scans WHERE enabled"))
        ]
        totals = {"scans": len(scan_ids), "signals": 0, "alerts_sent": 0}
        for scan_id in scan_ids:
            summary = await run_scan_pass(session, scan_id)
            totals["signals"] += len(summary["signals"])
            totals["alerts_sent"] += await dispatch_signals(session, summary["signals"])
        return totals

    await _log_run("hourly_scan_pass", body)


async def liquidity_rank() -> None:
    """19:00 IST: 30-day avg traded value → top-N ranks (drives top_liquid_50)."""

    async def body(session):
        result = await session.execute(
            text(
                "INSERT INTO liquidity_stats (symbol_id, asof_date, avg_traded_value_30d, rank) "
                "SELECT symbol_id, CURRENT_DATE, avg_tv, "
                "       rank() OVER (ORDER BY avg_tv DESC) "
                "FROM ( "
                "  SELECT symbol_id, avg(c * v) AS avg_tv FROM candles "
                "  WHERE tf = '1D' AND ts > now() - interval '30 days' "
                "    AND symbol_id IN (SELECT id FROM symbols WHERE fno_flag) "
                "  GROUP BY symbol_id "
                ") t "
                "ON CONFLICT (symbol_id, asof_date) DO UPDATE "
                "SET avg_traded_value_30d = excluded.avg_traded_value_30d, "
                "    rank = excluded.rank"
            )
        )
        await session.commit()
        return {"ranked": result.rowcount}

    await _log_run("liquidity_rank", body)


async def signal_outcomes() -> None:
    """19:45 IST: label past signals with 1/5/20-day forward returns."""

    async def body(session):
        result = await session.execute(
            text(
                "UPDATE signals sig SET "
                "  return_1d = fwd.r1, return_5d = fwd.r5, return_20d = fwd.r20, "
                "  outcomes_labeled_at = now() "
                "FROM ( "
                "  SELECT sig2.id, "
                "    (SELECT (c.c - base.c) / base.c * 100 FROM candles c "
                "     WHERE c.symbol_id = sig2.symbol_id AND c.tf = '1D' "
                "       AND c.ts >= sig2.ts + interval '1 day' ORDER BY c.ts LIMIT 1) r1, "
                "    (SELECT (c.c - base.c) / base.c * 100 FROM candles c "
                "     WHERE c.symbol_id = sig2.symbol_id AND c.tf = '1D' "
                "       AND c.ts >= sig2.ts + interval '5 days' ORDER BY c.ts LIMIT 1) r5, "
                "    (SELECT (c.c - base.c) / base.c * 100 FROM candles c "
                "     WHERE c.symbol_id = sig2.symbol_id AND c.tf = '1D' "
                "       AND c.ts >= sig2.ts + interval '20 days' ORDER BY c.ts LIMIT 1) r20 "
                "  FROM signals sig2 "
                "  JOIN LATERAL (SELECT c.c FROM candles c "
                "    WHERE c.symbol_id = sig2.symbol_id AND c.tf = '1D' "
                "      AND c.ts <= sig2.ts ORDER BY c.ts DESC LIMIT 1) base ON true "
                "  WHERE sig2.outcomes_labeled_at IS NULL "
                "    AND sig2.ts < now() - interval '1 day' "
                ") fwd WHERE sig.id = fwd.id"
            )
        )
        await session.commit()
        return {"labeled": result.rowcount}

    await _log_run("signal_outcomes", body)


async def _is_holiday(session, d: date) -> bool:
    if d.weekday() >= 5:  # Sat/Sun
        return True
    row = await session.execute(
        text(
            "SELECT 1 FROM market_holidays WHERE exchange = 'NSE' AND holiday_date = :d"
        ),
        {"d": d},
    )
    return row.first() is not None

"""APScheduler entrypoint — `python -m app.workers.scheduler`.

Job table (docs/ARCHITECTURE.md §6, all times IST). All jobs are idempotent
and log to public.job_runs. Weekend/holiday skips happen inside the job
bodies (jobs.py checks market_holidays).
"""

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.workers import jobs

IST = "Asia/Kolkata"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=IST)
    # refresh free Yahoo data at :10 so the :15 scan pass sees current bars
    scheduler.add_job(
        jobs.yahoo_intraday_refresh,
        CronTrigger(day_of_week="mon-fri", hour="10-15", minute=10, timezone=IST),
        id="yahoo_intraday_refresh",
    )
    # hourly candle closes: 10:15, 11:15, 12:15, 13:15, 14:15, 15:15 + 15:30 close
    scheduler.add_job(
        jobs.hourly_scan_pass,
        CronTrigger(day_of_week="mon-fri", hour="10-15", minute=15, timezone=IST),
        id="hourly_scan_pass",
    )
    scheduler.add_job(
        jobs.hourly_scan_pass,
        CronTrigger(day_of_week="mon-fri", hour=15, minute=30, timezone=IST),
        id="close_scan_pass",
    )
    scheduler.add_job(
        jobs.eod_bhavcopy,
        CronTrigger(day_of_week="mon-fri", hour=18, minute=30, timezone=IST),
        id="eod_bhavcopy",
    )
    scheduler.add_job(
        jobs.liquidity_rank,
        CronTrigger(day_of_week="mon-fri", hour=19, minute=0, timezone=IST),
        id="liquidity_rank",
    )
    scheduler.add_job(
        jobs.signal_outcomes,
        CronTrigger(day_of_week="mon-fri", hour=19, minute=45, timezone=IST),
        id="signal_outcomes",
    )
    return scheduler


async def main() -> None:
    scheduler = build_scheduler()
    scheduler.start()
    logging.getLogger(__name__).info(
        "worker scheduler started: %s", [j.id for j in scheduler.get_jobs()]
    )
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())

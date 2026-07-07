"""APScheduler entrypoint — `python -m app.workers.scheduler`.

Job table (docs/ARCHITECTURE.md §6, all times IST):
  hourly_scan_pass   10:15..15:15 + 15:30   run all enabled scans
  chain_snapshot     every 5 min, mkt hours option chains → chain_snapshots
  eod_bhavcopy       18:30 daily            EOD ingest, universe/ban/lot refresh
  liquidity_rank     19:00 daily            30d avg traded value → top-50 ranks
  reconcile          19:30 daily            broker vs bhavcopy close check
  news_poll          every 10 min           RSS fetch + dedupe
  iv_daily_close     15:35 daily            ATM IV close → iv_history
  signal_outcomes    19:45 daily            label signals with fwd returns

All jobs must be idempotent and log to public.job_runs.
"""

import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler

IST = "Asia/Kolkata"


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=IST)
    # Jobs are registered here as they ship, e.g.:
    # scheduler.add_job(jobs.hourly_scan_pass, "cron",
    #                   day_of_week="mon-fri", hour="10-15", minute=15)
    return scheduler


async def main() -> None:
    scheduler = build_scheduler()
    scheduler.start()
    print("worker scheduler started")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())

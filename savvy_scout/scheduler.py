"""Background jobs for a production deploy: the daily sweep and a daily
backup, run in-process inside the web service.

Why in-process rather than a separate Render Cron Job: the sweep and the
web dashboard both need the SAME SQLite file, and Render persistent disks
can only be attached to one service at a time -- a separate Cron Job
service couldn't share the web service's disk. Running it on a timer
inside the same process (same pattern as the sibling app, see
new-app/scheduler.py) sidesteps that entirely, at the cost of needing
start_scheduler() called exactly once per running process -- see wsgi.py.

Locally, sweeping still runs via `python -m savvy_scout.cli sweep`
(e.g. from Windows Task Scheduler); this only matters for the deployed
copy, which has no OS-level scheduler to lean on.
"""

from __future__ import annotations

import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler

from savvy_scout.config import load_settings
from savvy_scout.db.backup import backup_database
from savvy_scout.db.connection import get_connection, init_db
from savvy_scout.db.seed_config import seed_all
from savvy_scout.sweep.runner import run_sweep

logger = logging.getLogger(__name__)

# 2026-08-10: the team works out of the Philippines -- 8am Manila time was
# chosen over an earlier 6am proposal specifically because it falls just
# after UK midnight (UK is 7-8 hours behind PH depending on BST/GMT), so the
# full previous UK calendar day's notices are already published by the time
# this runs. 6am PH would land an hour BEFORE UK midnight instead, risking
# missing anything published in the UK's last hour of that day. Explicit
# tzinfo rather than relying on the container's local time (previously
# unset, so hour=6 silently meant 6am UTC/7am BST -- not the "8am UK time"
# the Overview's own display text claimed, see home.py's sweep_next_run).
MANILA = ZoneInfo("Asia/Manila")


def run_daily_sweep() -> None:
    settings = load_settings()
    conn = get_connection(settings.db_path)
    try:
        init_db(conn)
        seed_all(conn)
        stats = run_sweep(conn, settings, triggered_by="scheduler")
        logger.info(
            "Scheduled sweep: pulled %s notices, %s expiring leads, %s triaged",
            stats["pulled"], stats["expiring_leads"], stats["triaged"],
        )
    finally:
        conn.close()


def run_daily_backup() -> None:
    settings = load_settings()
    try:
        path = backup_database(settings.db_path)
        logger.info("Scheduled backup written to %s", path)
    except FileNotFoundError:
        logger.warning("Scheduled backup skipped: no database file yet at %s", settings.db_path)


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_daily_sweep, "cron", hour=8, minute=0, timezone=MANILA, id="daily_sweep")
    scheduler.add_job(run_daily_backup, "cron", hour=5, minute=45, id="daily_backup")
    scheduler.start()
    return scheduler

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
from datetime import date
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler

from savvy_scout.config import load_settings
from savvy_scout.db.backup import backup_database
from savvy_scout.db.connection import get_connection, init_db
from savvy_scout.db.seed_config import seed_all
from savvy_scout.notifications import NotificationError, send_email_with_attachment
from savvy_scout.reporting.reports import generate_monthly_report, generate_weekly_report, most_recent_monday
from savvy_scout.sweep.runner import run_sweep

logger = logging.getLogger(__name__)

# Reports are prepared for Trifork's leadership team (UK-based), so their
# schedule runs on UK time rather than the team's own Manila time above.
LONDON = ZoneInfo("Europe/London")

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


def _email_report(path: str, subject: str) -> None:
    settings = load_settings()
    if not settings.report_recipient_email:
        logger.warning("Report generated at %s but REPORT_RECIPIENT_EMAIL is unset; not emailed.", path)
        return
    try:
        send_email_with_attachment(
            settings.report_recipient_email,
            subject,
            "Attached: the latest auto-generated Trifork Scouting report from Savvy Scout.",
            path,
        )
        logger.info("Emailed %s to %s", path, settings.report_recipient_email)
    except NotificationError:
        logger.exception("Failed to email report %s", path)


def run_weekly_report_job() -> None:
    """SPEC.md C6 Friday EOW report -- covers the current week (Monday
    through today) so Friday afternoon's send reflects the whole working
    week, not last week's."""
    settings = load_settings()
    conn = get_connection(settings.db_path)
    try:
        week_start = most_recent_monday()
        path = generate_weekly_report(conn, week_start, settings.reports_output_dir)
        _email_report(path, f"Trifork Scouting Weekly Report {week_start.isoformat()}")
    finally:
        conn.close()


def run_monthly_report_job() -> None:
    """Runs on the 1st of the month, so it reports the month that just
    finished rather than the (nearly empty) one just starting."""
    settings = load_settings()
    conn = get_connection(settings.db_path)
    try:
        today = date.today()
        if today.month == 1:
            month_start = date(today.year - 1, 12, 1)
        else:
            month_start = date(today.year, today.month - 1, 1)
        path = generate_monthly_report(conn, month_start, settings.reports_output_dir)
        _email_report(path, f"Trifork Scouting Monthly Report {month_start.strftime('%Y-%m')}")
    finally:
        conn.close()


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_daily_sweep, "cron", hour=8, minute=0, timezone=MANILA, id="daily_sweep")
    scheduler.add_job(run_daily_backup, "cron", hour=5, minute=45, id="daily_backup")
    scheduler.add_job(
        run_weekly_report_job, "cron", day_of_week="fri", hour=16, minute=0, timezone=LONDON, id="weekly_report"
    )
    scheduler.add_job(
        run_monthly_report_job, "cron", day=1, hour=8, minute=0, timezone=LONDON, id="monthly_report"
    )
    scheduler.start()
    return scheduler

"""Landing dashboard: a pipeline-health overview, separate from the
Approval Queue (SPEC.md B1's action list, now at /queue). Nothing here
changes state -- purely read-only counts and charts. "Needs attention" and
"Recent activity" now live as topbar notification dropdowns (see
dashboard/notifications.py + the context processor in dashboard/__init__.py)
rather than as panels on this page, so this view is scoped the same way the
queue is: sector owners see their own patch, Victoria sees everything.

2026-07-30: the scouting/sector numbers on this page are additionally scoped
to "clean" notices only -- a real sector match, within that sector's
configured CPV scope (config_sector_cpv_scope), and UK1-UK4 stage. This
matches what actually reaches an owner (everything else auto-rejects or
FLAGs as an open question, see triage.gates/workflow.approvals), so the
Overview reads as "what we're actually pursuing," not raw sweep volume."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, current_app, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from savvy_scout.dashboard.auth import get_db
from savvy_scout.dashboard.scope_filter import in_scope_filter_sql
from savvy_scout.sweep.runner import run_sweep

home_bp = Blueprint("home", __name__)

# Shared colour language for the Overview page's pie/donut charts -- the
# same colours are used for the legend swatches and the CSS conic-gradient
# background, so keeping them here (rather than duplicated in Jinja) is the
# single source of truth for both.
SECTOR_PALETTE = ["#2563EB", "#7C3AED", "#10B981", "#F59E0B", "#EC4899", "#14B8A6", "#64748B"]
TRIAGE_COLORS = {"PASS": "#10B981", "FLAG": "#F59E0B", "MAYBE": "#8B5CF6", "FAIL": "#DC2626"}


def _conic_gradient(shares: list[tuple[str, float]]) -> str:
    """Build a CSS conic-gradient() string from a list of (color, pct) slices
    (pct in 0..100). Used to render donut/pie charts with plain CSS -- no
    charting library or JS dependency needed."""
    stops = []
    acc = 0.0
    for color, pct in shares:
        if pct <= 0:
            continue
        start, acc = acc, acc + pct
        stops.append(f"{color} {start:.2f}% {acc:.2f}%")
    if not stops:
        return "conic-gradient(#E5E7EB 0% 100%)"
    return "conic-gradient(" + ", ".join(stops) + ")"


def _count(conn, query: str, params: tuple) -> int:
    return conn.execute(query, params).fetchone()[0]


def _pretty_date(value: datetime) -> str:
    return f"{value.day} {value:%b %Y}"


def _pretty_datetime(value: datetime) -> str:
    return value.strftime("%d %b %Y, %I:%M %p %Z")


@home_bp.route("/")
@login_required
def index():
    conn = get_db()
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    tomorrow_start = today_start + timedelta(days=1)
    week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    year_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

    in_scope_where, in_scope_params = in_scope_filter_sql(conn)

    scouting_total = _count(conn, f"SELECT COUNT(*) FROM notices WHERE {in_scope_where}", tuple(in_scope_params))
    scouting_ytd = _count(
        conn, f"SELECT COUNT(*) FROM notices WHERE {in_scope_where} AND first_seen_at >= ?",
        (*in_scope_params, year_start.isoformat()),
    )
    scouting_month = _count(
        conn, f"SELECT COUNT(*) FROM notices WHERE {in_scope_where} AND first_seen_at >= ?",
        (*in_scope_params, month_start.isoformat()),
    )
    scouting_week = _count(
        conn, f"SELECT COUNT(*) FROM notices WHERE {in_scope_where} AND first_seen_at >= ?",
        (*in_scope_params, week_start.isoformat()),
    )
    scouting_today = _count(
        conn, f"SELECT COUNT(*) FROM notices WHERE {in_scope_where} AND first_seen_at >= ?",
        (*in_scope_params, today_start.isoformat()),
    )
    scouting_yesterday = _count(
        conn,
        f"SELECT COUNT(*) FROM notices WHERE {in_scope_where} AND first_seen_at >= ? AND first_seen_at < ?",
        (*in_scope_params, yesterday_start.isoformat(), today_start.isoformat()),
    )
    swept_today = _count(
        conn,
        f"SELECT COUNT(*) FROM notices WHERE {in_scope_where} AND last_swept_at >= ? AND last_swept_at < ?",
        (*in_scope_params, today_start.isoformat(), tomorrow_start.isoformat()),
    )
    new_today = _count(
        conn,
        f"SELECT COUNT(*) FROM notices WHERE {in_scope_where} AND first_seen_at >= ? AND first_seen_at < ?",
        (*in_scope_params, today_start.isoformat(), tomorrow_start.isoformat()),
    )
    updated_today = _count(
        conn,
        f"SELECT COUNT(*) FROM notices WHERE {in_scope_where} "
        "AND last_swept_at >= ? AND last_swept_at < ? AND first_seen_at < ?",
        (*in_scope_params, today_start.isoformat(), tomorrow_start.isoformat(), today_start.isoformat()),
    )
    swept_yesterday = _count(
        conn,
        f"SELECT COUNT(*) FROM notices WHERE {in_scope_where} AND last_swept_at >= ? AND last_swept_at < ?",
        (*in_scope_params, yesterday_start.isoformat(), today_start.isoformat()),
    )

    last_swept_row = conn.execute(
        "SELECT MAX(last_swept_at) AS last_swept_at FROM notices WHERE last_swept_at IS NOT NULL"
    ).fetchone()
    sweep_last_run = None
    sweep_next_run = None
    try:
        uk_now = now.astimezone(ZoneInfo("Europe/London"))
        next_uk_run = uk_now.replace(hour=8, minute=0, second=0, microsecond=0)
        if uk_now >= next_uk_run:
            next_uk_run += timedelta(days=1)
        sweep_next_run = _pretty_datetime(next_uk_run)
    except Exception:
        sweep_next_run = "8:00 AM UK time daily"

    last_swept_at = last_swept_row["last_swept_at"] if last_swept_row else None
    if last_swept_at:
        try:
            last_swept_dt = datetime.fromisoformat(last_swept_at)
            sweep_last_run = _pretty_datetime(last_swept_dt.astimezone(ZoneInfo("Europe/London")))
        except Exception:
            sweep_last_run = last_swept_at

    sector_rows = conn.execute(
        f"""
        SELECT sector, COUNT(*) AS cnt
        FROM notices
        WHERE {in_scope_where}
        GROUP BY sector
        ORDER BY cnt DESC, sector ASC
        """,
        tuple(in_scope_params),
    ).fetchall()
    sector_split = [
        {
            "sector": row["sector"],
            "count": row["cnt"],
            "share": round((row["cnt"] / scouting_total * 100) if scouting_total else 0, 1),
        }
        for row in sector_rows
    ]
    sector_pie_gradient = _conic_gradient(
        [(SECTOR_PALETTE[i % len(SECTOR_PALETTE)], row["share"]) for i, row in enumerate(sector_split)]
    )

    # One row per sector (+ UNVERIFIED), each broken down by scouting window,
    # so "how are we doing per sector" and "how are we doing over time" are
    # answered by a single table instead of two disconnected panels.
    sector_time_query_rows = conn.execute(
        f"""
        SELECT sector,
               SUM(CASE WHEN first_seen_at >= ? THEN 1 ELSE 0 END) AS today_cnt,
               SUM(CASE WHEN first_seen_at >= ? THEN 1 ELSE 0 END) AS week_cnt,
               SUM(CASE WHEN first_seen_at >= ? THEN 1 ELSE 0 END) AS month_cnt,
               SUM(CASE WHEN first_seen_at >= ? THEN 1 ELSE 0 END) AS ytd_cnt,
               COUNT(*) AS total_cnt
        FROM notices
        WHERE {in_scope_where}
        GROUP BY sector
        ORDER BY total_cnt DESC, sector ASC
        """,
        (
            today_start.isoformat(), week_start.isoformat(), month_start.isoformat(), year_start.isoformat(),
            *in_scope_params,
        ),
    ).fetchall()
    sector_time_rows = [
        {
            "sector": row["sector"],
            "today": row["today_cnt"],
            "week": row["week_cnt"],
            "month": row["month_cnt"],
            "ytd": row["ytd_cnt"],
        }
        for row in sector_time_query_rows
    ]
    sector_time_rows.append(
        {
            "sector": "TOTAL",
            "today": scouting_today,
            "week": scouting_week,
            "month": scouting_month,
            "ytd": scouting_ytd,
        }
    )

    latest_triage_rows = conn.execute(
        f"""
        WITH latest AS (
            SELECT notice_id, MAX(id) AS max_id
            FROM triage_runs
            GROUP BY notice_id
        )
        SELECT tr.headline_outcome AS outcome, COUNT(*) AS cnt
        FROM triage_runs tr
        JOIN latest l ON l.max_id = tr.id
        JOIN notices n ON n.id = tr.notice_id
        WHERE {in_scope_where}
        GROUP BY tr.headline_outcome
        """,
        tuple(in_scope_params),
    ).fetchall()
    triage_totals = {row["outcome"]: row["cnt"] for row in latest_triage_rows}
    triage_order = ["PASS", "FLAG", "MAYBE", "FAIL"]
    triage_total = sum(triage_totals.values())
    triage_outcomes = [
        {
            "label": label,
            "value": triage_totals.get(label, 0),
            "share": round((triage_totals.get(label, 0) / triage_total * 100) if triage_total else 0, 1),
        }
        for label in triage_order
    ]
    triage_pie_gradient = _conic_gradient(
        [(TRIAGE_COLORS.get(item["label"], "#64748B"), item["share"]) for item in triage_outcomes]
    )

    scouting_report = {
        "total": scouting_total,
        "tiles": [
            {"label": "Scouted YTD", "value": scouting_ytd, "hint": f"Since {_pretty_date(year_start)}"},
            {"label": "This Month", "value": scouting_month, "hint": f"Since {_pretty_date(month_start)}"},
            {"label": "This Week", "value": scouting_week, "hint": f"Since {_pretty_date(week_start)}"},
            {"label": "Today", "value": scouting_today, "hint": f"Since {_pretty_date(today_start)}"},
        ],
        "daily": {
            "yesterday_seen": scouting_yesterday,
            "today_seen": scouting_today,
            "yesterday_swept": swept_yesterday,
            "today_swept": swept_today,
            "today_new": new_today,
            "today_updated": updated_today,
        },
        "sector_split": sector_split,
        "sector_time_rows": sector_time_rows,
        "sector_pie_gradient": sector_pie_gradient,
        "triage_outcomes": triage_outcomes,
        "triage_pie_gradient": triage_pie_gradient,
    }

    return render_template(
        "home.html",
        scouting_report=scouting_report,
        sweep_note={"last_run": sweep_last_run, "next_run": sweep_next_run},
        sector_palette=SECTOR_PALETTE,
        triage_colors=TRIAGE_COLORS,
    )


@home_bp.route("/sweep-now", methods=["POST"])
@login_required
def sweep_now():
    settings = current_app.config["SAVVY_SCOUT_SETTINGS"]
    conn = get_db()
    stats = run_sweep(conn, settings)
    flash(
        f"Sweep complete: pulled {stats['pulled']} notices, surfaced {stats['expiring_leads']} expiring leads, triaged {stats['triaged']} new notices.",
        "success",
    )
    return redirect(url_for("home.index"))

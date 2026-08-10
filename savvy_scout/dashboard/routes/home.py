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

import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, current_app, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from savvy_scout.dashboard.auth import get_db
from savvy_scout.dashboard.scope_filter import IN_SCOPE_UK_STAGES, in_scope_filter_sql
from savvy_scout.sweep.runner import get_recent_sweep_runs, run_sweep

home_bp = Blueprint("home", __name__)

LONDON = ZoneInfo("Europe/London")
WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri"]

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


def _to_london_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(LONDON)


def _report_date(row):
    """The date a notice counts under for Sector Performance: first_published_at
    (set once, on first insert, never touched again) if we have it, else the
    older published_at, else first_seen_at as a last-resort fallback for the
    rare notice a source published without a usable date. Deliberately NOT
    published_at first -- that's the source release's own "date" field, its
    LAST-UPDATED timestamp, which gets overwritten on every re-sweep. Without
    first_published_at, a 3-week-old notice amended/awarded/cancelled today
    would silently look newly published today (2026-08-10 finding). Never
    first_seen_at by default -- that's when OUR sweep found it, not when the
    buyer actually published it."""
    dt = (
        _to_london_datetime(row["first_published_at"])
        or _to_london_datetime(row["published_at"])
        or _to_london_datetime(row["first_seen_at"])
    )
    return dt.date() if dt else None


def _build_scope_predicate(conn):
    """Same "in scope" rule as scope_filter.in_scope_filter_sql (sector set,
    UK1-4 stage, within that sector's configured CPV scope), just as a
    Python predicate -- Sector Performance buckets by calendar day in
    Europe/London from a stored ISO timestamp with a mix of offsets, which
    isn't reliable to do in raw SQL, so the whole report is built in Python
    from one bulk fetch instead of one query per cell."""
    rows = conn.execute(
        "SELECT sector, allowed_cpv_prefixes FROM config_sector_cpv_scope WHERE enabled = 1"
    ).fetchall()
    if not rows:
        def predicate(sector, cpv_primary, uk_stage):
            return sector is not None and uk_stage in IN_SCOPE_UK_STAGES
        return predicate

    scope_map = {row["sector"]: json.loads(row["allowed_cpv_prefixes"]) for row in rows}

    def predicate(sector, cpv_primary, uk_stage):
        if uk_stage not in IN_SCOPE_UK_STAGES:
            return False
        prefixes = scope_map.get(sector)
        if prefixes is None:
            return False
        return bool(cpv_primary) and any(cpv_primary.startswith(p) for p in prefixes)

    return predicate


def _new_perf_bucket(weekdays):
    return {"days": {d: 0 for d in weekdays}, "week": 0, "month": 0, "ytd": 0}


def _accumulate_perf(bucket, report_date, weekdays, week_start, week_end, month_start, year_start):
    if report_date in bucket["days"]:
        bucket["days"][report_date] += 1
    if week_start <= report_date <= week_end:
        bucket["week"] += 1
    if report_date >= month_start:
        bucket["month"] += 1
    if report_date >= year_start:
        bucket["ytd"] += 1


def _perf_row(label, bucket, weekdays, **extra):
    return {
        "sector": label,
        "days": [bucket["days"][d] for d in weekdays],
        "week": bucket["week"],
        "month": bucket["month"],
        "ytd": bucket["ytd"],
        **extra,
    }


def _perf_windows(now_uk: datetime):
    """Shared Mon-Fri-this-week + week/month/YTD window boundaries for every
    Overview performance table (Sector, Source, ...), so they all report
    against the exact same date ranges."""
    today = now_uk.date()
    week_start = today - timedelta(days=now_uk.weekday())
    week_end = week_start + timedelta(days=6)
    weekdays = [week_start + timedelta(days=i) for i in range(5)]
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)
    return weekdays, week_start, week_end, month_start, year_start


def _day_headers(weekdays):
    return [{"label": label, "date": _pretty_date(d)} for label, d in zip(WEEKDAY_LABELS, weekdays)]


def _build_sector_performance(conn, now_uk: datetime) -> dict:
    """Sector Performance (2026-08-09): per-sector opportunity counts for
    Mon-Fri of the CURRENT week, then This Week/This Month/YTD, dated by
    publication date (not sweep date). Two grand-total rows are appended:
    "In Sector" (sum of the per-sector rows above, i.e. what in_scope_filter_sql
    also counts) and "Total Swept" (every notice pulled, matched to a sector
    or not) -- comparing the two shows how much of the raw sweep volume
    actually lands in-scope."""
    weekdays, week_start, week_end, month_start, year_start = _perf_windows(now_uk)

    predicate = _build_scope_predicate(conn)
    rows = conn.execute(
        "SELECT sector, cpv_primary, uk_stage, first_published_at, published_at, first_seen_at FROM notices"
    ).fetchall()

    sector_buckets: dict[str, dict] = {}
    in_scope_total = _new_perf_bucket(weekdays)
    swept_total = _new_perf_bucket(weekdays)

    for row in rows:
        report_date = _report_date(row)
        if report_date is None:
            continue
        _accumulate_perf(swept_total, report_date, weekdays, week_start, week_end, month_start, year_start)

        if predicate(row["sector"], row["cpv_primary"], row["uk_stage"]):
            _accumulate_perf(in_scope_total, report_date, weekdays, week_start, week_end, month_start, year_start)
            bucket = sector_buckets.setdefault(row["sector"], _new_perf_bucket(weekdays))
            _accumulate_perf(bucket, report_date, weekdays, week_start, week_end, month_start, year_start)

    perf_rows = [
        _perf_row(sector, bucket, weekdays)
        for sector, bucket in sorted(sector_buckets.items(), key=lambda kv: kv[1]["ytd"], reverse=True)
    ]
    perf_rows.append(_perf_row("In Sector (total)", in_scope_total, weekdays, is_total=True))
    perf_rows.append(_perf_row("Total Swept (all sources)", swept_total, weekdays, is_total=True, is_grand_total=True))

    return {"rows": perf_rows, "day_headers": _day_headers(weekdays)}


def _build_upcoming_deadlines(conn, in_scope_where, in_scope_params, limit=8) -> list[dict]:
    """Nearest submission deadlines across every sector (2026-08-09), so
    urgency is visible regardless of who owns the notice -- the per-owner
    queues already sort by deadline, but only within one person's own
    sector(s)."""
    today = datetime.now(timezone.utc).date().isoformat()
    rows = conn.execute(
        f"""
        SELECT id, ref, title, buyer, sector, owner, deadline
        FROM notices
        WHERE {in_scope_where} AND deadline IS NOT NULL AND deadline >= ?
        ORDER BY deadline ASC
        LIMIT ?
        """,
        (*in_scope_params, today, limit),
    ).fetchall()
    return [
        {
            "id": r["id"], "ref": r["ref"], "title": r["title"], "buyer": r["buyer"],
            "sector": r["sector"], "owner": r["owner"], "deadline": r["deadline"][:10],
        }
        for r in rows
    ]


# Cumulative pipeline funnel (2026-08-09): each stage's count includes every
# notice that has REACHED that stage or gone further, not just notices
# currently sitting there -- e.g. "Escalated" also counts Approved/Capture
# Brief Drafted/etc, since those all passed through Escalated on the way.
# That's what makes it a funnel (monotonically non-increasing bars) instead
# of just the current status breakdown Sector Performance/Opportunities
# already show.
_FUNNEL_STAGES = [
    ("Phase 1 Triaged", None),  # every in-scope notice except still-NEW
    ("Phase 2 Scoped", (
        "PHASE2_SCOPED", "AWAITING_PHASE2_APPROVAL", "ESCALATED_TO_VICTORIA",
        "APPROVED", "CAPTURE_BRIEF_DRAFTED", "DOCS_DOWNLOADED", "CALENDARED", "ACTIVE",
    )),
    ("Escalated to Victoria", (
        "ESCALATED_TO_VICTORIA", "APPROVED", "CAPTURE_BRIEF_DRAFTED",
        "DOCS_DOWNLOADED", "CALENDARED", "ACTIVE",
    )),
    ("Approved", ("APPROVED", "CAPTURE_BRIEF_DRAFTED", "DOCS_DOWNLOADED", "CALENDARED", "ACTIVE")),
]


def _build_pipeline_funnel(conn, in_scope_where, in_scope_params) -> dict:
    rows = conn.execute(
        f"SELECT status, COUNT(*) AS cnt FROM notices WHERE {in_scope_where} GROUP BY status",
        tuple(in_scope_params),
    ).fetchall()
    counts = {r["status"]: r["cnt"] for r in rows}
    total = sum(counts.values())

    stages = [{"label": "Swept (in scope)", "value": total}]
    for label, statuses in _FUNNEL_STAGES:
        value = (total - counts.get("NEW", 0)) if statuses is None else sum(counts.get(s, 0) for s in statuses)
        stages.append({"label": label, "value": value})

    max_value = stages[0]["value"] or 1
    for stage in stages:
        stage["pct"] = round(stage["value"] / max_value * 100, 1) if max_value else 0

    return {
        "stages": stages,
        "rejected": counts.get("REJECTED", 0),
        "parked": counts.get("PARKED", 0),
        "monitoring": counts.get("MONITORING", 0),
    }


# "Open" = still needs someone's attention or active bid work -- excludes
# terminal/closed-out statuses (Rejected, Parked, Monitoring, Active) so a
# backlog reads as "notices still moving through the pipeline," not
# "everything ever assigned to this person."
_OPEN_STATUSES = (
    "TO_REVIEW", "HANDOFF", "PHASE2_SCOPED", "AWAITING_PHASE2_APPROVAL",
    "ESCALATED_TO_VICTORIA", "APPROVED", "CAPTURE_BRIEF_DRAFTED", "DOCS_DOWNLOADED", "CALENDARED",
)


def _build_owner_workload(conn, in_scope_where, in_scope_params) -> list[dict]:
    placeholders = ", ".join("?" for _ in _OPEN_STATUSES)
    rows = conn.execute(
        f"""
        SELECT owner, COUNT(*) AS cnt
        FROM notices
        WHERE {in_scope_where} AND owner IS NOT NULL AND status IN ({placeholders})
        GROUP BY owner
        ORDER BY cnt DESC
        """,
        (*in_scope_params, *_OPEN_STATUSES),
    ).fetchall()
    return [{"owner": r["owner"], "count": r["cnt"]} for r in rows]


def _build_contract_expiry_radar(conn, limit=8) -> list[dict]:
    """Soonest-expiring incumbent contracts (2026-07's expiry radar, see
    sweep/expiry_radar.py) -- re-procurement leads, a separate feed from
    fresh notices, worth surfacing on the same Overview since they're the
    same kind of "opportunity to watch for.\""""
    today = datetime.now(timezone.utc).date().isoformat()
    rows = conn.execute(
        """
        SELECT notice_ref, buyer, title, end_date, review_date
        FROM contract_expiry
        WHERE end_date >= ?
        ORDER BY end_date ASC
        LIMIT ?
        """,
        (today, limit),
    ).fetchall()
    return [
        {
            "notice_ref": r["notice_ref"], "buyer": r["buyer"], "title": r["title"],
            "end_date": r["end_date"][:10], "review_date": r["review_date"][:10],
        }
        for r in rows
    ]


def _build_top_buyers(conn, in_scope_where, in_scope_params, limit=8) -> list[dict]:
    rows = conn.execute(
        f"""
        SELECT buyer, COUNT(*) AS cnt
        FROM notices
        WHERE {in_scope_where} AND buyer IS NOT NULL
        GROUP BY buyer
        ORDER BY cnt DESC, buyer ASC
        LIMIT ?
        """,
        (*in_scope_params, limit),
    ).fetchall()
    max_count = rows[0]["cnt"] if rows else 1
    return [{"buyer": r["buyer"], "count": r["cnt"], "pct": round(r["cnt"] / max_count * 100, 1)} for r in rows]


def _build_source_performance(conn, now_uk: datetime) -> dict:
    """Notices by Source (2026-08-09): where each swept notice actually came
    from (Find a Tender, Contracts Finder, Public Contracts Scotland,
    Sell2Wales, eTendersNI -- see sources/ and config_sources), same
    Mon-Fri/week/month/YTD shape as Sector Performance, dated by publication
    date. Unfiltered by sector/CPV scope -- this is about sweep coverage per
    source, not what's in scope, so it should total to the same "Total
    Swept" figure Sector Performance shows."""
    weekdays, week_start, week_end, month_start, year_start = _perf_windows(now_uk)

    rows = conn.execute(
        "SELECT source, first_published_at, published_at, first_seen_at FROM notices"
    ).fetchall()

    source_buckets: dict[str, dict] = {}
    grand_total = _new_perf_bucket(weekdays)

    for row in rows:
        report_date = _report_date(row)
        if report_date is None:
            continue
        _accumulate_perf(grand_total, report_date, weekdays, week_start, week_end, month_start, year_start)
        bucket = source_buckets.setdefault(row["source"] or "Unknown", _new_perf_bucket(weekdays))
        _accumulate_perf(bucket, report_date, weekdays, week_start, week_end, month_start, year_start)

    perf_rows = [
        _perf_row(source, bucket, weekdays)
        for source, bucket in sorted(source_buckets.items(), key=lambda kv: kv[1]["ytd"], reverse=True)
    ]
    perf_rows.append(_perf_row("Total", grand_total, weekdays, is_total=True, is_grand_total=True))

    return {"rows": perf_rows, "day_headers": _day_headers(weekdays)}


@home_bp.route("/")
@login_required
def index():
    conn = get_db()
    now = datetime.now(timezone.utc)
    uk_now = now.astimezone(LONDON)
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
            sweep_last_run = _pretty_datetime(last_swept_dt.astimezone(LONDON))
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

    # Sector Performance (2026-08-09): dated by publication date, not sweep
    # date -- see _build_sector_performance. Built once here rather than as
    # several more SQL queries, since bucketing by Europe/London calendar day
    # from a stored ISO timestamp with mixed UTC offsets isn't reliable to do
    # in raw SQL.
    sector_performance = _build_sector_performance(conn, uk_now)
    source_performance = _build_source_performance(conn, uk_now)
    upcoming_deadlines = _build_upcoming_deadlines(conn, in_scope_where, in_scope_params)
    pipeline_funnel = _build_pipeline_funnel(conn, in_scope_where, in_scope_params)
    owner_workload = _build_owner_workload(conn, in_scope_where, in_scope_params)
    contract_expiry_radar = _build_contract_expiry_radar(conn)
    top_buyers = _build_top_buyers(conn, in_scope_where, in_scope_params)
    sweep_history = get_recent_sweep_runs(conn)

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
        "sector_pie_gradient": sector_pie_gradient,
        "triage_outcomes": triage_outcomes,
        "triage_pie_gradient": triage_pie_gradient,
    }

    return render_template(
        "home.html",
        scouting_report=scouting_report,
        sector_performance=sector_performance,
        source_performance=source_performance,
        upcoming_deadlines=upcoming_deadlines,
        pipeline_funnel=pipeline_funnel,
        owner_workload=owner_workload,
        contract_expiry_radar=contract_expiry_radar,
        top_buyers=top_buyers,
        sweep_history=sweep_history,
        sweep_note={"last_run": sweep_last_run, "next_run": sweep_next_run},
        sector_palette=SECTOR_PALETTE,
        triage_colors=TRIAGE_COLORS,
    )


@home_bp.route("/sweep-now", methods=["POST"])
@login_required
def sweep_now():
    settings = current_app.config["SAVVY_SCOUT_SETTINGS"]
    conn = get_db()
    stats = run_sweep(conn, settings, triggered_by=current_user.display_name)
    flash(
        f"Sweep complete: pulled {stats['pulled']} notices, surfaced {stats['expiring_leads']} expiring leads, triaged {stats['triaged']} new notices.",
        "success",
    )
    return redirect(url_for("home.index"))

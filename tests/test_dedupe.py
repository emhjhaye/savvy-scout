from savvy_scout.models.notice import Notice
from savvy_scout.sources.ocds_parser import ParsedNotice
from savvy_scout.sweep.dedupe import upsert_notice


def _make_parsed(ref: str, title: str, buyer: str, published_at: str | None = None) -> ParsedNotice:
    notice = Notice(
        ref=ref,
        title=title,
        buyer=buyer,
        source="Find a Tender",
        notice_type="UK3",
        uk_stage="UK3",
        raw_json="{}",
        published_at=published_at,
    )
    return ParsedNotice(notice=notice, text_blob=title.lower(), tender_status="active")


def test_exact_ref_match_updates_not_duplicates(conn):
    first = _make_parsed("REF-001", "Payments Platform Refresh", "Some Bank")
    notice_id_1 = upsert_notice(conn, first)

    updated = _make_parsed("REF-001", "Payments Platform Refresh (updated)", "Some Bank")
    notice_id_2 = upsert_notice(conn, updated)

    assert notice_id_1 == notice_id_2
    count = conn.execute("SELECT COUNT(*) AS n FROM notices").fetchone()["n"]
    assert count == 1
    title = conn.execute("SELECT title FROM notices WHERE id = ?", (notice_id_1,)).fetchone()["title"]
    assert title == "Payments Platform Refresh (updated)"


def test_fuzzy_title_buyer_match_updates_not_duplicates(conn):
    first = _make_parsed("REF-100", "Real Time Payments Clearing Platform", "Vocalink Limited")
    notice_id_1 = upsert_notice(conn, first)

    # Same opportunity, resurfaced under a different reference, near-identical
    # title and buyer.
    relisted = _make_parsed("REF-200", "Real Time Payments Clearing Platform ", "Vocalink Ltd")
    notice_id_2 = upsert_notice(conn, relisted)

    assert notice_id_1 == notice_id_2
    count = conn.execute("SELECT COUNT(*) AS n FROM notices").fetchone()["n"]
    assert count == 1


def test_distinct_notices_are_not_merged(conn):
    first = _make_parsed("REF-A", "Smart Grid Telemetry Upgrade", "National Grid")
    second = _make_parsed("REF-B", "Airline Booking System Replacement", "A Regional Airline")

    id_a = upsert_notice(conn, first)
    id_b = upsert_notice(conn, second)

    assert id_a != id_b
    count = conn.execute("SELECT COUNT(*) AS n FROM notices").fetchone()["n"]
    assert count == 2


def test_first_published_at_set_on_insert(conn):
    first = _make_parsed("REF-300", "Legal Advisory Services", "Home Office", published_at="2026-07-20T09:00:00")
    notice_id = upsert_notice(conn, first)

    row = conn.execute(
        "SELECT published_at, first_published_at FROM notices WHERE id = ?", (notice_id,)
    ).fetchone()
    assert row["published_at"] == "2026-07-20T09:00:00"
    assert row["first_published_at"] == "2026-07-20T09:00:00"


def test_first_published_at_survives_amendment_but_published_at_updates(conn):
    """An amendment/award/cancellation re-releases the notice with today's
    date -- published_at should track that (it's genuinely the source's
    last-updated timestamp), but first_published_at must stay pinned to
    when the notice was first seen, or Sector Performance/Notices by
    Source would count a 3-week-old notice as newly published today
    (2026-08-10 finding)."""
    first = _make_parsed("REF-301", "Fleet Vehicle Maintenance", "Home Office", published_at="2026-07-20T09:00:00")
    notice_id = upsert_notice(conn, first)

    amended = _make_parsed(
        "REF-301", "Fleet Vehicle Maintenance (AMENDED)", "Home Office", published_at="2026-08-10T11:00:00"
    )
    same_id = upsert_notice(conn, amended)

    assert same_id == notice_id
    row = conn.execute(
        "SELECT published_at, first_published_at FROM notices WHERE id = ?", (notice_id,)
    ).fetchone()
    assert row["published_at"] == "2026-08-10T11:00:00"
    assert row["first_published_at"] == "2026-07-20T09:00:00"

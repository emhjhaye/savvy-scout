from savvy_scout.models.notice import Notice
from savvy_scout.sources.ocds_parser import ParsedNotice
from savvy_scout.sweep.dedupe import upsert_notice


def _make_parsed(
    ref: str, title: str, buyer: str, published_at: str | None = None, is_publish_event: bool = True,
) -> ParsedNotice:
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
    return ParsedNotice(
        notice=notice, text_blob=title.lower(), tender_status="active", is_publish_event=is_publish_event,
    )


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


def test_award_only_first_discovery_leaves_publish_date_unknown(conn):
    """2026-08-10 finding #2, same day as the amendment fix above: a notice
    discovered for the very first time via an award/contract/amendment/
    termination release (is_publish_event=False) has no reliable publish
    date anywhere in that release's payload -- first_published_at must stay
    NULL and publish_date_unknown must be set, or Sector Performance/
    Notices by Source would still mis-date it as "published today" (the day
    WE happened to first see it) via the published_at/first_seen_at
    fallback, same failure as finding #1 just via a different path."""
    award_only = _make_parsed(
        "REF-400", "Fleet Vehicle Maintenance", "Home Office",
        published_at="2026-08-10T09:50:00", is_publish_event=False,
    )
    notice_id = upsert_notice(conn, award_only)

    row = conn.execute(
        "SELECT published_at, first_published_at, publish_date_unknown FROM notices WHERE id = ?",
        (notice_id,),
    ).fetchone()
    assert row["published_at"] == "2026-08-10T09:50:00"
    assert row["first_published_at"] is None
    assert row["publish_date_unknown"] == 1


def test_later_genuine_tender_release_self_heals_publish_date_unknown(conn):
    """The far rarer reverse order -- we first met this notice via an
    award-only release (unknown date), and a LATER re-sweep turns up an
    actual tender/planning release for the same ref. That's real evidence
    we didn't have before, so it should backfill first_published_at and
    clear publish_date_unknown rather than leaving the notice permanently
    excluded from date-based reporting."""
    award_only = _make_parsed(
        "REF-401", "Fleet Vehicle Maintenance", "Home Office",
        published_at="2026-08-10T09:50:00", is_publish_event=False,
    )
    notice_id = upsert_notice(conn, award_only)

    genuine_tender = _make_parsed(
        "REF-401", "Fleet Vehicle Maintenance", "Home Office",
        published_at="2026-08-11T10:00:00", is_publish_event=True,
    )
    same_id = upsert_notice(conn, genuine_tender)

    assert same_id == notice_id
    row = conn.execute(
        "SELECT published_at, first_published_at, publish_date_unknown FROM notices WHERE id = ?",
        (notice_id,),
    ).fetchone()
    assert row["first_published_at"] == "2026-08-11T10:00:00"
    assert row["publish_date_unknown"] == 0


def test_award_update_on_known_good_notice_does_not_flip_to_unknown(conn):
    """The far more common order -- a genuinely-new tender notice later gets
    an award update. publish_date_unknown must stay 0 and
    first_published_at must stay pinned to the original date; the award
    update should only move published_at."""
    tender = _make_parsed(
        "REF-402", "Fleet Vehicle Maintenance", "Home Office",
        published_at="2026-07-20T09:00:00", is_publish_event=True,
    )
    notice_id = upsert_notice(conn, tender)

    award_update = _make_parsed(
        "REF-402", "Fleet Vehicle Maintenance (AWARDED)", "Home Office",
        published_at="2026-08-10T09:50:00", is_publish_event=False,
    )
    same_id = upsert_notice(conn, award_update)

    assert same_id == notice_id
    row = conn.execute(
        "SELECT published_at, first_published_at, publish_date_unknown FROM notices WHERE id = ?",
        (notice_id,),
    ).fetchone()
    assert row["published_at"] == "2026-08-10T09:50:00"
    assert row["first_published_at"] == "2026-07-20T09:00:00"
    assert row["publish_date_unknown"] == 0


def test_award_update_does_not_regress_uk_stage_to_unverified(conn):
    """2026-08-10 finding #3: an award/contract/termination release has no
    notice document at all, so notice_type comes back None on that update
    -- previously this unconditionally overwrote the notice's real UK1-4
    stage with UNVERIFIED, which silently drops it out of every in-scope
    view (Opportunities, owner queues, Victoria's Approved list) the moment
    an already-tracked, possibly-already-approved notice gets awarded. The
    award release provided no stage information, so the existing one must
    be kept, not erased."""
    tender = _make_parsed("REF-403", "Fleet Vehicle Maintenance", "Home Office", is_publish_event=True)
    tender.notice.notice_type = "UK2"
    tender.notice.uk_stage = "UK2"
    notice_id = upsert_notice(conn, tender)
    conn.execute("UPDATE notices SET status = 'APPROVED' WHERE id = ?", (notice_id,))
    conn.commit()

    award_update = _make_parsed(
        "REF-403", "Fleet Vehicle Maintenance (AWARDED)", "Home Office", is_publish_event=False,
    )
    award_update.notice.notice_type = None
    award_update.notice.uk_stage = "UNVERIFIED"
    same_id = upsert_notice(conn, award_update)

    assert same_id == notice_id
    row = conn.execute(
        "SELECT status, uk_stage, notice_type FROM notices WHERE id = ?", (notice_id,)
    ).fetchone()
    assert row["status"] == "APPROVED"
    assert row["uk_stage"] == "UK2"
    assert row["notice_type"] == "UK2"

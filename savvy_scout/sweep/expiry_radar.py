"""Expiry radar (SPEC.md A2): sweeps award notices in scope sectors, logs
contract end dates, and surfaces anything ending within 18 months as a
future re-procurement lead with a review date."""

import sqlite3
from datetime import datetime, timedelta, timezone

from savvy_scout.logging_util import log_audit
from savvy_scout.sources.ocds_parser import ParsedNotice
from savvy_scout.triage.sector_classifier import classify_sector

EXPIRY_LOOKAHEAD_DAYS = 18 * 30
REVIEW_LEAD_DAYS = 6 * 30


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def surface_if_expiring(conn: sqlite3.Connection, parsed: ParsedNotice) -> bool:
    """Returns True if this award notice was surfaced as a future
    re-procurement lead. Only considers award notices in a configured
    ("scope") sector; buyers matching no sector are skipped, not guessed."""
    if not parsed.is_award or not parsed.contract_end_date:
        return False

    sector = classify_sector(conn, parsed.notice.buyer, parsed.text_blob)
    if sector is None:
        return False

    end_date = _parse_date(parsed.contract_end_date)
    if not end_date:
        return False

    now = datetime.now(end_date.tzinfo) if end_date.tzinfo else datetime.now(timezone.utc)
    if end_date > now + timedelta(days=EXPIRY_LOOKAHEAD_DAYS):
        return False

    review_date = end_date - timedelta(days=REVIEW_LEAD_DAYS)
    existing = conn.execute(
        "SELECT id FROM contract_expiry WHERE notice_ref = ?", (parsed.notice.ref,)
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE contract_expiry SET buyer = ?, title = ?, end_date = ?, review_date = ? "
            "WHERE id = ?",
            (
                parsed.notice.buyer,
                parsed.notice.title,
                parsed.contract_end_date,
                review_date.isoformat(),
                existing["id"],
            ),
        )
    else:
        conn.execute(
            "INSERT INTO contract_expiry "
            "(notice_ref, buyer, title, end_date, review_date, source_ref, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                parsed.notice.ref,
                parsed.notice.buyer,
                parsed.notice.title,
                parsed.contract_end_date,
                review_date.isoformat(),
                parsed.notice.ref,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    conn.commit()
    log_audit(
        conn,
        "contract_expiry",
        parsed.notice.ref,
        "expiry_surfaced",
        "system_sweep",
        f"Contract end date {parsed.contract_end_date} is within {EXPIRY_LOOKAHEAD_DAYS} days, "
        f"sector {sector}, review date {review_date.date().isoformat()}",
    )
    return True

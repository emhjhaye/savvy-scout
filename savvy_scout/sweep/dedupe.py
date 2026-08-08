"""Dedupe and cross-check (SPEC.md A2): before creating a row, check the
notice reference AND fuzzy-match title plus buyer against all existing rows,
so the same opportunity surfacing under a different listing updates the
existing row rather than creating a duplicate."""

import json
import sqlite3
from datetime import datetime, timezone

from rapidfuzz import fuzz

from savvy_scout.logging_util import log_audit, log_status_change
from savvy_scout.models.notice import Status
from savvy_scout.sources.ocds_parser import ParsedNotice

FUZZY_MATCH_THRESHOLD = 88

# Extra OCDS fields (2026-07-30): column name -> Notice attribute name, for
# the ones that don't need special conversion (see _additional_field_values
# for above_threshold, which does).
_ADDITIONAL_FIELDS = [
    "value_amount_gross",
    "main_procurement_category",
    "enquiry_period_end",
    "award_period_end",
    "submission_method_details",
    "submission_languages",
    "electronic_submission_policy",
    "procedure_features",
    "award_criteria_summary",
    "contract_start_date",
    "contract_max_extent_date",
    "renewal_description",
    "buyer_ppon",
    "buyer_website",
    "buyer_org_type",
    "conflicts_assessment",
    "bid_documents_json",
]


def _additional_field_values(notice) -> list:
    above_threshold = notice.above_threshold
    return [int(above_threshold) if above_threshold is not None else None] + [
        getattr(notice, field) for field in _ADDITIONAL_FIELDS
    ]


def find_existing_notice(conn: sqlite3.Connection, parsed: ParsedNotice) -> sqlite3.Row | None:
    ref = parsed.notice.ref
    exact = conn.execute("SELECT * FROM notices WHERE ref = ?", (ref,)).fetchone()
    if exact:
        return exact

    title = (parsed.notice.title or "").lower()
    buyer = (parsed.notice.buyer or "").lower()
    if not title:
        return None

    best_row = None
    best_score = 0.0
    for candidate in conn.execute("SELECT * FROM notices").fetchall():
        title_score = fuzz.token_sort_ratio(title, (candidate["title"] or "").lower())
        if buyer and candidate["buyer"]:
            buyer_score = fuzz.token_sort_ratio(buyer, candidate["buyer"].lower())
            combined = title_score * 0.7 + buyer_score * 0.3
        else:
            combined = title_score
        if combined > best_score:
            best_score = combined
            best_row = candidate

    if best_row is not None and best_score >= FUZZY_MATCH_THRESHOLD:
        return best_row
    return None


def _insert_notice(conn, notice, parsed, cpv_additional_json, lot_statuses_json, now, actor) -> int:
    additional_cols = ["above_threshold"] + _ADDITIONAL_FIELDS
    columns = (
        "ref, ocid, title, buyer, source, notice_type, uk_stage, status, "
        "indicative_value, cpv_primary, cpv_primary_inferred, cpv_additional, deadline, "
        "cpv_primary_description, supplier_name, supplier_address, buyer_address, "
        "buyer_contact_email, buyer_region, procurement_method, procurement_method_details, notice_url, "
        f"{', '.join(additional_cols)}, "
        "text_blob, tender_status, lot_statuses, tender_period_end, pme_due_date, "
        "future_notice_date, contract_end_date, is_award, raw_json, "
        "first_seen_at, last_swept_at, created_at, updated_at"
    )
    num_columns = len(columns.split(","))
    cursor = conn.execute(
        f"INSERT INTO notices ({columns}) VALUES ({', '.join('?' for _ in range(num_columns))})",
        (
            notice.ref,
            notice.ocid,
            notice.title,
            notice.buyer,
            notice.source,
            notice.notice_type,
            notice.uk_stage,
            Status.NEW.value,
            notice.indicative_value,
            notice.cpv_primary,
            int(notice.cpv_primary_inferred),
            cpv_additional_json,
            notice.deadline,
            notice.cpv_primary_description,
            notice.supplier_name,
            notice.supplier_address,
            notice.buyer_address,
            notice.buyer_contact_email,
            notice.buyer_region,
            notice.procurement_method,
            notice.procurement_method_details,
            notice.notice_url,
            *_additional_field_values(notice),
            parsed.text_blob,
            parsed.tender_status,
            lot_statuses_json,
            parsed.tender_period_end,
            parsed.pme_due_date,
            parsed.future_notice_date,
            parsed.contract_end_date,
            int(parsed.is_award),
            notice.raw_json,
            now,
            now,
            now,
            now,
        ),
    )
    notice_id = cursor.lastrowid
    conn.commit()
    log_status_change(conn, notice_id, None, Status.NEW.value, actor, "First seen on sweep")
    log_audit(conn, "notice", str(notice_id), "notice_created", actor, f"New notice {notice.ref}")
    return notice_id


def upsert_notice(conn: sqlite3.Connection, parsed: ParsedNotice, actor: str = "system_sweep") -> int:
    """Inserts a new notice row, or updates an existing one found by ref or
    fuzzy title+buyer match. Returns the notice id."""
    existing = find_existing_notice(conn, parsed)
    now = datetime.now(timezone.utc).isoformat()
    notice = parsed.notice

    cpv_additional_json = json.dumps(notice.cpv_additional or [])
    lot_statuses_json = json.dumps(parsed.lot_statuses or [])

    if existing is None:
        try:
            return _insert_notice(conn, notice, parsed, cpv_additional_json, lot_statuses_json, now, actor)
        except sqlite3.IntegrityError:
            # Same ref inserted twice within one sweep (e.g. an OCDS source's
            # pagination handing back an overlapping page boundary) -- the
            # first insert already committed it, so what looked like "new" a
            # moment ago now exists. Don't let one collision abort the whole
            # source's remaining notices; fall through to the update path
            # against the row that must now exist.
            conn.rollback()
            existing = conn.execute("SELECT * FROM notices WHERE ref = ?", (notice.ref,)).fetchone()
            if existing is None:
                raise

    notice_id = existing["id"]
    match_kind = "exact ref match" if existing["ref"] == notice.ref else "fuzzy title/buyer match"
    additional_cols = ["above_threshold"] + _ADDITIONAL_FIELDS
    conn.execute(
        "UPDATE notices SET "
        "ocid = ?, title = ?, buyer = ?, notice_type = ?, uk_stage = ?, "
        "indicative_value = ?, cpv_primary = ?, cpv_primary_inferred = ?, cpv_additional = ?, "
        "deadline = ?, cpv_primary_description = ?, supplier_name = ?, supplier_address = ?, "
        "buyer_address = ?, buyer_contact_email = ?, buyer_region = ?, procurement_method = ?, "
        "procurement_method_details = ?, notice_url = ?, "
        f"{', '.join(f'{c} = ?' for c in additional_cols)}, "
        "text_blob = ?, tender_status = ?, lot_statuses = ?, "
        "tender_period_end = ?, pme_due_date = ?, future_notice_date = ?, contract_end_date = ?, "
        "is_award = ?, raw_json = ?, last_swept_at = ?, updated_at = ? "
        "WHERE id = ?",
        (
            notice.ocid,
            notice.title,
            notice.buyer,
            notice.notice_type,
            notice.uk_stage,
            notice.indicative_value,
            notice.cpv_primary,
            int(notice.cpv_primary_inferred),
            cpv_additional_json,
            notice.deadline,
            notice.cpv_primary_description,
            notice.supplier_name,
            notice.supplier_address,
            notice.buyer_address,
            notice.buyer_contact_email,
            notice.buyer_region,
            notice.procurement_method,
            notice.procurement_method_details,
            notice.notice_url,
            *_additional_field_values(notice),
            parsed.text_blob,
            parsed.tender_status,
            lot_statuses_json,
            parsed.tender_period_end,
            parsed.pme_due_date,
            parsed.future_notice_date,
            parsed.contract_end_date,
            int(parsed.is_award),
            notice.raw_json,
            now,
            now,
            notice_id,
        ),
    )
    conn.commit()
    log_audit(
        conn,
        "notice",
        str(notice_id),
        "notice_updated",
        actor,
        f"Updated via {match_kind} against incoming ref {notice.ref}",
    )
    return notice_id

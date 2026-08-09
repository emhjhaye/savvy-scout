import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema)
    _apply_migrations(conn)
    conn.commit()


def _apply_migrations(conn: sqlite3.Connection) -> None:
    # v1.5 status rename migration
    status_map = {
        "AWAITING_PHASE1_APPROVAL": "TO_REVIEW",
        "MONITOR": "MONITORING",
    }
    for old_status, new_status in status_map.items():
        conn.execute("UPDATE notices SET status = ? WHERE status = ?", (new_status, old_status))
        conn.execute("UPDATE status_history SET from_status = ? WHERE from_status = ?", (new_status, old_status))
        conn.execute("UPDATE status_history SET to_status = ? WHERE to_status = ?", (new_status, old_status))

    # v1.5 escalation docs: internal addendum vs capture brief marker
    cols = [r[1] for r in conn.execute("PRAGMA table_info(escalation_briefs)").fetchall()]
    if "brief_type" not in cols:
        conn.execute("ALTER TABLE escalation_briefs ADD COLUMN brief_type TEXT NOT NULL DEFAULT 'INTERNAL_ADDENDUM'")

    # Full-detail notice fields: supplier, contracting authority contact/
    # address, procurement method/regime, human-readable CPV description --
    # previously only buried in raw_json, not queryable or displayable.
    notice_cols = [r[1] for r in conn.execute("PRAGMA table_info(notices)").fetchall()]
    new_notice_cols = [
        "cpv_primary_description",
        "supplier_name",
        "supplier_address",
        "buyer_address",
        "buyer_contact_email",
        "buyer_region",
        "procurement_method",
        "procurement_method_details",
    ]
    for col in new_notice_cols:
        if col not in notice_cols:
            conn.execute(f"ALTER TABLE notices ADD COLUMN {col} TEXT")

    # Direct link to the published notice (Find a Tender / Contracts Finder),
    # so reviewers can check the source directly from the Capture Brief.
    # Backfilled from each notice's already-stored raw_json rather than
    # constructed/guessed, since the URL is only trustworthy if the source
    # actually published it.
    if "notice_url" not in notice_cols:
        conn.execute("ALTER TABLE notices ADD COLUMN notice_url TEXT")

    if "auto_rejected_unowned" not in notice_cols:
        conn.execute("ALTER TABLE notices ADD COLUMN auto_rejected_unowned INTEGER NOT NULL DEFAULT 0")

    rows_missing_url = conn.execute(
        "SELECT id, raw_json FROM notices WHERE notice_url IS NULL AND raw_json IS NOT NULL AND raw_json != ''"
    ).fetchall()
    if rows_missing_url:
        import json as _json

        from savvy_scout.sources.ocds_parser import _find_notice_url

        for row in rows_missing_url:
            try:
                release = _json.loads(row["raw_json"])
            except ValueError:
                continue
            url = _find_notice_url(release)
            if url:
                conn.execute("UPDATE notices SET notice_url = ? WHERE id = ?", (url, row["id"]))

    # Additional OCDS fields (award criteria, submission instructions,
    # contract start/extension dates, buyer PPON/website/org type, etc.),
    # 2026-07-30: present in raw_json all along, never parsed out before.
    # Backfilled from each notice's already-stored raw_json, not just
    # applied to future sweeps, so existing notices get this too.
    additional_cols = [
        "value_amount_gross", "above_threshold", "main_procurement_category",
        "enquiry_period_end", "award_period_end", "submission_method_details",
        "submission_languages", "electronic_submission_policy", "procedure_features",
        "award_criteria_summary", "contract_start_date", "contract_max_extent_date",
        "renewal_description", "buyer_ppon", "buyer_website", "buyer_org_type",
        "conflicts_assessment", "bid_documents_json",
    ]
    missing_additional_cols = [c for c in additional_cols if c not in notice_cols]
    for col in missing_additional_cols:
        col_type = "INTEGER" if col == "above_threshold" else "TEXT"
        conn.execute(f"ALTER TABLE notices ADD COLUMN {col} {col_type}")

    # Account management (2026-08-08): email column for login-by-email and
    # invite emails, is_admin for the new account-management screen (Mark,
    # deliberately separate from is_victoria's existing rule-correction
    # authority). Existing seeded accounts keep username login working since
    # email is nullable; 'mark' is granted is_admin on the migration that
    # actually adds the column, not unconditionally, so a superadmin flag set
    # by hand later isn't clobbered by a later boot.
    user_cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "email" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
    if "is_admin" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
        conn.execute("UPDATE users SET is_admin = 1 WHERE username = 'mark'")

    # Teams notifications (2026-08-09): a per-user Microsoft Teams incoming
    # webhook URL, so a new-opportunity notification can be posted straight
    # into that owner's Teams alongside the email -- no Azure AD app
    # registration needed (the Graph app-registration for this app was never
    # completed, see notifications.py), just a webhook connector the owner
    # adds to a channel/chat of their choosing and pastes the URL for here.
    if "teams_webhook_url" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN teams_webhook_url TEXT")

    if missing_additional_cols:
        import json as _json

        from savvy_scout.sources.ocds_parser import extract_additional_fields

        rows_to_backfill = conn.execute(
            "SELECT id, raw_json FROM notices WHERE raw_json IS NOT NULL AND raw_json != ''"
        ).fetchall()
        for row in rows_to_backfill:
            try:
                release = _json.loads(row["raw_json"])
            except ValueError:
                continue
            fields = extract_additional_fields(release)
            conn.execute(
                "UPDATE notices SET value_amount_gross = ?, above_threshold = ?, "
                "main_procurement_category = ?, enquiry_period_end = ?, award_period_end = ?, "
                "submission_method_details = ?, submission_languages = ?, "
                "electronic_submission_policy = ?, procedure_features = ?, "
                "award_criteria_summary = ?, contract_start_date = ?, contract_max_extent_date = ?, "
                "renewal_description = ?, buyer_ppon = ?, buyer_website = ?, buyer_org_type = ?, "
                "conflicts_assessment = ?, bid_documents_json = ? WHERE id = ?",
                (
                    fields["value_amount_gross"], fields["above_threshold"],
                    fields["main_procurement_category"], fields["enquiry_period_end"],
                    fields["award_period_end"], fields["submission_method_details"],
                    fields["submission_languages"], fields["electronic_submission_policy"],
                    fields["procedure_features"], fields["award_criteria_summary"],
                    fields["contract_start_date"], fields["contract_max_extent_date"],
                    fields["renewal_description"], fields["buyer_ppon"], fields["buyer_website"],
                    fields["buyer_org_type"], fields["conflicts_assessment"],
                    fields["bid_documents_json"], row["id"],
                ),
            )

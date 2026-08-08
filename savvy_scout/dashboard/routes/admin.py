"""Admin tab: config table editing + the B4 learning loop's rule-correction
log. Restricted to Victoria and Kanvesh (flagged in the plan; SPEC.md B4
doesn't name who besides Victoria has this authority, and the references name
Kanvesh as the process owner). A bare-bones version now; SPEC.md C5 (source
tier management, email whitelist) completes it later."""

from datetime import datetime, timezone

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from savvy_scout.dashboard.auth import get_db
from savvy_scout.logging_util import log_audit

admin_bp = Blueprint("admin", __name__)

EDITABLE_TABLES = [
    "config_owner_map",
    "config_sector_keywords",
    "config_gate2_terms",
    "config_coupling_terms",
    "config_exclusion_terms",
    "config_framework_keywords",
    "config_trifork_frameworks",
    "config_cpv_lists",
    "config_sector_cpv_scope",
    "config_scale_filter",
    "config_capability_profile",
    "config_sources",
]

# Groups the flat EDITABLE_TABLES list into related sections for the admin
# page's nav + layout: (anchor slug, section label, table names in it).
TABLE_GROUPS = [
    ("sectors", "Sectors & Owners", ["config_owner_map", "config_sector_keywords", "config_exclusion_terms"]),
    ("gate2", "Type of Work (Gate 2)", ["config_gate2_terms", "config_coupling_terms"]),
    ("frameworks", "Framework Rules", ["config_framework_keywords", "config_trifork_frameworks"]),
    ("cpv", "CPV & Scale", ["config_cpv_lists", "config_sector_cpv_scope", "config_scale_filter"]),
    ("capability", "Capability Profile", ["config_capability_profile"]),
    ("sources", "Sweep Sources", ["config_sources"]),
]

# Columns the app manages itself (autoincrement PK, or audit timestamps/actor
# stamped server-side) -- never rendered as editable inputs, never taken from
# submitted form data.
AUTO_MANAGED_COLUMNS = {"id", "updated_at", "updated_by", "created_at"}


def _has_correction_authority() -> bool:
    return current_user.display_name in ("Victoria", "Kanvesh")


def _table_schema(conn, table_name: str) -> list[dict]:
    """User-editable columns for a table: name, whether it's NOT NULL with
    no default (so a blank submission must be rejected, not silently
    inserted as an empty string)."""
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return [
        {
            "name": row["name"],
            "required": bool(row["notnull"]) and row["dflt_value"] is None,
        }
        for row in rows
        if row["name"] not in AUTO_MANAGED_COLUMNS
    ]


def _record_correction(conn, table_name: str, description: str, reason: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO rule_corrections (entered_by, entered_at, table_affected, description, reason, source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (current_user.display_name, now, table_name, description, reason, None),
    )
    conn.commit()
    log_audit(conn, "config", table_name, "settings_change", current_user.display_name, reason)


@admin_bp.route("/")
@login_required
def index():
    if not _has_correction_authority():
        flash("Only Victoria and Kanvesh can make rule corrections.", "error")
        return redirect(url_for("queues.index"))
    conn = get_db()
    tables = {name: conn.execute(f"SELECT * FROM {name}").fetchall() for name in EDITABLE_TABLES}
    editable_columns = {name: _table_schema(conn, name) for name in EDITABLE_TABLES}
    corrections = conn.execute(
        "SELECT * FROM rule_corrections ORDER BY id DESC LIMIT 50"
    ).fetchall()
    return render_template(
        "admin.html",
        tables=tables,
        editable_columns=editable_columns,
        corrections=corrections,
        groups=TABLE_GROUPS,
    )


@admin_bp.route("/config/<table_name>/<int:row_id>/update", methods=["POST"])
@login_required
def update_row(table_name, row_id):
    if not _has_correction_authority():
        flash("Only Victoria and Kanvesh can make rule corrections.", "error")
        return redirect(url_for("queues.index"))
    if table_name not in EDITABLE_TABLES:
        flash("Unknown config table.", "error")
        return redirect(url_for("admin.index"))

    reason = request.form.get("reason", "")
    if not reason.strip():
        flash("A reason is required for every rule correction.", "error")
        return redirect(url_for("admin.index"))

    conn = get_db()
    editable_names = {col["name"] for col in _table_schema(conn, table_name)}
    columns = [c for c in request.form if c != "reason" and c in editable_names]
    if not columns:
        flash("No recognised fields submitted.", "error")
        return redirect(url_for("admin.index"))

    all_column_names = {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
    set_clause_parts = [f"{c} = ?" for c in columns]
    values = [request.form[c] for c in columns]
    if "updated_at" in all_column_names:
        set_clause_parts.append("updated_at = ?")
        values.append(datetime.now(timezone.utc).isoformat())
    if "updated_by" in all_column_names:
        set_clause_parts.append("updated_by = ?")
        values.append(current_user.display_name)
    conn.execute(
        f"UPDATE {table_name} SET {', '.join(set_clause_parts)} WHERE id = ?", (*values, row_id)
    )
    conn.commit()

    _record_correction(conn, table_name, f"Updated row {row_id}, fields: {', '.join(columns)}", reason)
    flash("Rule correction saved.")
    return redirect(url_for("admin.index"))


@admin_bp.route("/config/<table_name>/add", methods=["POST"])
@login_required
def add_row(table_name):
    if not _has_correction_authority():
        flash("Only Victoria and Kanvesh can make rule corrections.", "error")
        return redirect(url_for("queues.index"))
    if table_name not in EDITABLE_TABLES:
        flash("Unknown config table.", "error")
        return redirect(url_for("admin.index"))

    reason = request.form.get("reason", "")
    if not reason.strip():
        flash("A reason is required for every rule correction.", "error")
        return redirect(url_for("admin.index"))

    conn = get_db()
    schema = _table_schema(conn, table_name)

    values_by_column = {}
    missing_required = []
    for col in schema:
        value = request.form.get(col["name"], "").strip()
        if value:
            values_by_column[col["name"]] = value
        elif col["required"]:
            missing_required.append(col["name"])

    if missing_required:
        flash(f"Missing required field(s): {', '.join(missing_required)}.", "error")
        return redirect(url_for("admin.index"))
    if not values_by_column:
        flash("Enter at least one field to add a new row.", "error")
        return redirect(url_for("admin.index"))

    all_column_names = {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
    now = datetime.now(timezone.utc).isoformat()
    if "updated_at" in all_column_names:
        values_by_column["updated_at"] = now
    if "updated_by" in all_column_names:
        values_by_column["updated_by"] = current_user.display_name
    if "created_at" in all_column_names:
        values_by_column["created_at"] = now

    columns = list(values_by_column.keys())
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})",
        [values_by_column[c] for c in columns],
    )
    conn.commit()

    description = ", ".join(f"{k}={v}" for k, v in values_by_column.items() if k not in AUTO_MANAGED_COLUMNS)
    _record_correction(conn, table_name, f"Added row: {description}", reason)
    flash("New row added.")
    return redirect(url_for("admin.index"))


@admin_bp.route("/config/<table_name>/<int:row_id>/delete", methods=["POST"])
@login_required
def delete_row(table_name, row_id):
    if not _has_correction_authority():
        flash("Only Victoria and Kanvesh can make rule corrections.", "error")
        return redirect(url_for("queues.index"))
    if table_name not in EDITABLE_TABLES:
        flash("Unknown config table.", "error")
        return redirect(url_for("admin.index"))

    reason = request.form.get("reason", "")
    if not reason.strip():
        flash("A reason is required for every rule correction.", "error")
        return redirect(url_for("admin.index"))

    conn = get_db()
    row = conn.execute(f"SELECT * FROM {table_name} WHERE id = ?", (row_id,)).fetchone()
    if row is None:
        flash("Row not found.", "error")
        return redirect(url_for("admin.index"))

    description = ", ".join(
        f"{k}={row[k]}" for k in row.keys() if k not in AUTO_MANAGED_COLUMNS and k != "id"
    )
    conn.execute(f"DELETE FROM {table_name} WHERE id = ?", (row_id,))
    conn.commit()

    _record_correction(conn, table_name, f"Deleted row {row_id}: {description}", reason)
    flash("Row deleted.")
    return redirect(url_for("admin.index"))

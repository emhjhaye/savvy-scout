import json
import os
import sqlite3
from copy import copy
from datetime import datetime, timezone
from pathlib import Path

from openpyxl import load_workbook

from savvy_scout.escalation.context import MISSING, OWNER_NAMES, build_context

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "artifacts" / "pipeline_tracker_template.xlsx"
TRACKER_SHEETS = ("Pass", "Flag", "Fail")
CLEAR_SHEETS = TRACKER_SHEETS + ("Pass to Kanvesh", "Pass to NHS")
HEADERS = (
    "REF #", "DATE SPOTTED", "OPPORTUNITY TITLE", "BUYER", "BUYER TYPE", "SECTOR",
    "SOURCE", "NOTICE TYPE", "INDICATIVE VALUE", "CPV CODES",
    "SUBMISSION/ENGAGEMENT DEADLINE", "TRIAGE STATUS", "CAPABILITY FIT",
    "FRAMEWORK STATUS", "FILTER FLAGS (1/2/3)", "REASON / NOTES", "NEXT ACTION",
    "NEXT ACTION DATE", "OPEN FLAGS FOR VICTORIA",
)


def _owner_reviewed_notice_ids(conn: sqlite3.Connection) -> list[int]:
    placeholders = ",".join("?" for _ in OWNER_NAMES)
    rows = conn.execute(
        f"SELECT notice_id, MAX(id) latest_id FROM status_history "
        f"WHERE from_status = 'AWAITING_PHASE2_APPROVAL' "
        f"AND to_status IN ('ESCALATED_TO_VICTORIA', 'REJECTED') "
        f"AND changed_by IN ({placeholders}) "
        f"AND EXISTS (SELECT 1 FROM phase2_assessments p WHERE p.notice_id = status_history.notice_id) "
        f"GROUP BY notice_id ORDER BY latest_id",
        OWNER_NAMES,
    ).fetchall()
    return [row["notice_id"] for row in rows]


def _decision_target(conn, notice_id):
    placeholders = ",".join("?" for _ in OWNER_NAMES)
    return conn.execute(
        f"SELECT to_status, reason FROM status_history WHERE notice_id = ? "
        f"AND from_status = 'AWAITING_PHASE2_APPROVAL' "
        f"AND to_status IN ('ESCALATED_TO_VICTORIA', 'REJECTED') "
        f"AND changed_by IN ({placeholders}) ORDER BY id DESC LIMIT 1",
        (notice_id, *OWNER_NAMES),
    ).fetchone()


def _target_sheet(context, decision):
    if decision["to_status"] == "REJECTED":
        return "Fail"
    return "Pass" if context["ai_read"]["overall"] == "PURSUE" else "Flag"


def _row_values(context, decision):
    reasoning = context["ai_read"].get("per_field_reasoning", {})
    questions = context["ai_read"].get("open_questions", [])
    return [
        context["notice_reference"],
        context["published_date"],
        context["title"],
        context["buyer"],
        MISSING,
        context["sector"],
        context["source_portal"],
        MISSING,
        f"{context['value_estimate']} {context['currency']}" if context["value_estimate"] != MISSING else MISSING,
        "; ".join(context["cpv_codes"]) or MISSING,
        context["submission_deadline"],
        _target_sheet(context, decision).upper(),
        f"{context['ai_read']['capability_fit']}: {reasoning.get('capability_fit', MISSING)}",
        context["framework_status"],
        MISSING,
        reasoning.get("overall", decision["reason"] or MISSING),
        "Victoria to make GO / NO-GO / Park decision" if decision["to_status"] != "REJECTED" else "Closed after owner Phase 2 review",
        context["submission_deadline"] if decision["to_status"] != "REJECTED" else MISSING,
        " | ".join(str(value) for value in questions) or MISSING,
    ]


def _snapshot_styles(workbook):
    snapshots = {}
    for sheet_name in TRACKER_SHEETS:
        sheet = workbook[sheet_name]
        source_row = 3
        snapshots[sheet_name] = [copy(sheet.cell(source_row, column)._style) for column in range(1, 20)]
    return snapshots


def _clear_sample_rows(workbook):
    for sheet_name in CLEAR_SHEETS:
        sheet = workbook[sheet_name]
        for row in range(3, sheet.max_row + 1):
            for column in range(1, 20):
                sheet.cell(row, column).value = None
                sheet.cell(row, column).hyperlink = None


def _template_or_existing(output: Path):
    if output.exists():
        workbook = load_workbook(output)
        headers = tuple(workbook["Flag"].cell(2, column).value for column in range(1, 20))
        if headers == HEADERS:
            return workbook, False
    return load_workbook(TEMPLATE_PATH), True


def update_trifork_pipeline(conn: sqlite3.Connection, output_path: str) -> dict[str, int | str]:
    output = Path(output_path)
    workbook, fresh = _template_or_existing(output)
    styles = _snapshot_styles(workbook)
    if fresh:
        _clear_sample_rows(workbook)

    existing = {}
    for sheet_name in TRACKER_SHEETS:
        sheet = workbook[sheet_name]
        for row in range(3, sheet.max_row + 1):
            reference = sheet.cell(row, 1).value
            if reference:
                existing[str(reference)] = (sheet_name, row)

    inserted = updated = skipped = 0
    for notice_id in _owner_reviewed_notice_ids(conn):
        context = build_context(conn, notice_id)
        if any(context[key] == MISSING for key in ("notice_reference", "title", "buyer", "sector", "owner_name")):
            skipped += 1
            continue
        decision = _decision_target(conn, notice_id)
        target_name = _target_sheet(context, decision)
        reference = context["notice_reference"]
        old = existing.get(reference)
        if old:
            old_sheet, old_row = old
            if old_sheet != target_name:
                for column in range(1, 20):
                    workbook[old_sheet].cell(old_row, column).value = None
                old = None
        if old:
            row_number = old[1]
            updated += 1
        else:
            target = workbook[target_name]
            occupied = [row for row in range(3, target.max_row + 1) if target.cell(row, 1).value]
            row_number = max(occupied, default=2) + 1
            inserted += 1
        sheet = workbook[target_name]
        for column, value in enumerate(_row_values(context, decision), start=1):
            cell = sheet.cell(row_number, column)
            cell._style = copy(styles[target_name][column - 1])
            cell.value = value
        existing[reference] = (target_name, row_number)

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp.xlsx")
    workbook.save(temporary)
    temporary.replace(output)
    return {
        "inserted": inserted, "updated": updated, "skipped": skipped,
        "total": len(existing), "output_path": str(output),
    }


def update_configured_trifork_pipeline(conn: sqlite3.Connection):
    output_path = os.environ.get("TRIFORK_PIPELINE_OUTPUT_PATH")
    return update_trifork_pipeline(conn, output_path) if output_path else None

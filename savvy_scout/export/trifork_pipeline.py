import json
import os
import re
import sqlite3
from copy import copy
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

TRACKER_SHEETS = ("Pass", "Flag", "Fail")
OWNER_NAMES = ("Mark", "Kanvesh", "Hammad")
HEADERS = (
    "REF #", "DATE SPOTTED", "OPPORTUNITY TITLE", "BUYER", "BUYER TYPE",
    "SECTOR", "SOURCE", "NOTICE TYPE", "INDICATIVE VALUE", "CPV CODES",
    "SUBMISSION/ENGAGEMENT DEADLINE", "TRIAGE STATUS", "CAPABILITY FIT",
    "FRAMEWORK STATUS", "FILTER FLAGS (1/2/3)", "REASON / NOTES",
    "NEXT ACTION", "NEXT ACTION DATE", "OPEN FLAGS FOR VICTORIA",
)


def _normalise(value) -> str:
    return " ".join(str(value or "").casefold().split())


def _decision_rows(conn: sqlite3.Connection) -> list[dict]:
    placeholders = ",".join("?" for _ in OWNER_NAMES)
    decisions = conn.execute(
        f"""
        SELECT sh.notice_id, sh.to_status, sh.changed_by, sh.changed_at, sh.reason
        FROM status_history sh
        WHERE sh.from_status = 'AWAITING_PHASE2_APPROVAL'
          AND sh.to_status IN ('ESCALATED_TO_VICTORIA', 'REJECTED')
          AND sh.changed_by IN ({placeholders})
        ORDER BY sh.changed_at, sh.id
        """,
        OWNER_NAMES,
    ).fetchall()

    latest_by_notice = {row["notice_id"]: row for row in decisions}
    rows = []
    for notice_id, decision in latest_by_notice.items():
        notice = conn.execute("SELECT * FROM notices WHERE id = ?", (notice_id,)).fetchone()
        if notice is None:
            continue
        assessment = conn.execute(
            "SELECT * FROM phase2_assessments WHERE notice_id = ? ORDER BY id DESC LIMIT 1",
            (notice_id,),
        ).fetchone()
        gate3 = conn.execute(
            "SELECT outcome, reason FROM gate_results WHERE notice_id = ? AND gate_number = 'gate3' "
            "ORDER BY id DESC LIMIT 1",
            (notice_id,),
        ).fetchone()
        row = dict(notice)
        row["decision"] = dict(decision)
        row["assessment"] = dict(assessment) if assessment else None
        row["gate3"] = dict(gate3) if gate3 else None
        rows.append(row)
    return rows


def _target_sheet(row: dict) -> str:
    if row["decision"]["to_status"] == "REJECTED":
        return "Fail"
    rating = (row["assessment"] or {}).get("overall_rating")
    return "Pass" if rating == "PURSUE" else "Flag"


def _json_list(value) -> list:
    if not value:
        return []
    try:
        result = json.loads(value)
        return result if isinstance(result, list) else []
    except (TypeError, ValueError):
        return []


def _cpv_text(row: dict) -> str:
    codes = [row.get("cpv_primary")] + _json_list(row.get("cpv_additional"))
    return ";".join(dict.fromkeys(str(code) for code in codes if code)) or "UNVERIFIED"


def _capability_fit(row: dict) -> str:
    assessment = row["assessment"]
    if not assessment:
        return "UNVERIFIED: no Phase 2 assessment recorded"
    rating = assessment.get("capability_fit_rating") or "UNVERIFIED"
    reasoning = assessment.get("capability_fit_reasoning") or ""
    return f"{rating}: {reasoning}".rstrip(": ")


def _open_questions(row: dict) -> str:
    assessment = row["assessment"]
    if not assessment:
        return ""
    return " | ".join(str(item) for item in _json_list(assessment.get("open_questions")))


def _row_values(row: dict, tracker_ref: str) -> list:
    decision = row["decision"]
    assessment = row["assessment"] or {}
    target = _target_sheet(row)
    approved = target != "Fail"
    framework = row["gate3"] or {}
    return [
        tracker_ref,
        (row.get("first_seen_at") or "")[:10],
        row.get("title"),
        row.get("buyer") or "UNVERIFIED",
        row.get("buyer_org_type") or "UNVERIFIED",
        row.get("sector") or "UNVERIFIED",
        row.get("source"),
        row.get("notice_type") or row.get("uk_stage") or "UNVERIFIED",
        row.get("indicative_value") or "Not stated",
        _cpv_text(row),
        (row.get("deadline") or "")[:10] or "UNVERIFIED",
        target.upper(),
        _capability_fit(row),
        f"{framework.get('outcome', 'UNVERIFIED')}: {framework.get('reason', '')}".rstrip(": "),
        "Clean",
        assessment.get("overall_reasoning") if approved else decision.get("reason"),
        "Victoria to make final go/no-go decision" if approved else "Closed after owner Phase 2 review",
        (decision.get("changed_at") or "")[:10],
        _open_questions(row) if approved else "",
    ]


def _max_tracker_number(workbook) -> int:
    maximum = 0
    for sheet in workbook.worksheets:
        for cell in sheet["A"]:
            match = re.fullmatch(r"N(\d+)", str(cell.value or "").strip())
            if match:
                maximum = max(maximum, int(match.group(1)))
    return maximum


def _existing_rows(workbook) -> dict[tuple[str, str], tuple[str, int, str]]:
    existing = {}
    for sheet_name in TRACKER_SHEETS:
        sheet = workbook[sheet_name]
        for row_number in range(3, sheet.max_row + 1):
            title = sheet.cell(row_number, 3).value
            buyer = sheet.cell(row_number, 4).value
            if title:
                existing[(_normalise(title), _normalise(buyer))] = (
                    sheet_name, row_number, str(sheet.cell(row_number, 1).value or "")
                )
    return existing


def _copy_row_style(source_sheet, source_row: int, target_sheet, target_row: int) -> None:
    target_sheet.row_dimensions[target_row].height = source_sheet.row_dimensions[source_row].height
    for column in range(1, len(HEADERS) + 1):
        source = source_sheet.cell(source_row, column)
        target = target_sheet.cell(target_row, column)
        if source.has_style:
            target._style = copy(source._style)
        target.number_format = source.number_format
        target.alignment = copy(source.alignment)


def update_trifork_pipeline(
    conn: sqlite3.Connection, template_path: str, output_path: str
) -> dict[str, int | str]:
    template = Path(template_path)
    output = Path(output_path)
    if not template.exists():
        raise FileNotFoundError(f"Trifork pipeline template not found: {template}")
    if template.resolve() == output.resolve():
        raise ValueError("Trifork pipeline template and output must be different files")

    workbook = load_workbook(template)
    for sheet_name in TRACKER_SHEETS:
        headers = tuple(workbook[sheet_name].cell(2, column).value for column in range(1, 20))
        if headers != HEADERS:
            raise ValueError(f"Unexpected columns in tracker sheet {sheet_name}")

    style_sheet = workbook["Flag"]
    style_row = 3
    existing = _existing_rows(workbook)
    next_number = _max_tracker_number(workbook) + 1
    decisions = _decision_rows(conn)
    counts = {"Pass": 0, "Flag": 0, "Fail": 0}

    removals: dict[str, list[int]] = {name: [] for name in TRACKER_SHEETS}
    prepared = []
    for row in decisions:
        key = (_normalise(row.get("title")), _normalise(row.get("buyer")))
        match = existing.get(key)
        if match:
            old_sheet, old_row, tracker_ref = match
            removals[old_sheet].append(old_row)
        else:
            tracker_ref = f"N{next_number:03d}"
            next_number += 1
        prepared.append((row, tracker_ref))

    for sheet_name, row_numbers in removals.items():
        sheet = workbook[sheet_name]
        for row_number in sorted(set(row_numbers), reverse=True):
            sheet.delete_rows(row_number)

    for row, tracker_ref in prepared:
        target_name = _target_sheet(row)
        target = workbook[target_name]
        target_row = max(target.max_row + 1, 3)
        _copy_row_style(style_sheet, style_row, target, target_row)
        for column, value in enumerate(_row_values(row, tracker_ref), start=1):
            target.cell(target_row, column).value = value
        counts[target_name] += 1

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp.xlsx")
    workbook.save(temporary)
    temporary.replace(output)
    return {**counts, "total": len(prepared), "output_path": str(output)}


def update_configured_trifork_pipeline(conn: sqlite3.Connection) -> dict[str, int | str] | None:
    template_path = os.environ.get("TRIFORK_PIPELINE_TEMPLATE_PATH")
    output_path = os.environ.get("TRIFORK_PIPELINE_OUTPUT_PATH")
    if not template_path or not output_path:
        return None
    return update_trifork_pipeline(conn, template_path, output_path)
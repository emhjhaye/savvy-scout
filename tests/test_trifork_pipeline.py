import hashlib
from copy import copy
from datetime import datetime, timezone

import pytest
from openpyxl import Workbook, load_workbook

from savvy_scout.export.trifork_pipeline import HEADERS, update_trifork_pipeline


def _insert_notice(conn, ref, title, buyer, status, rating=None):
    now = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        "INSERT INTO notices (ref, title, buyer, source, uk_stage, status, sector, owner, "
        "cpv_primary, first_seen_at, last_swept_at, created_at, updated_at, raw_json) "
        "VALUES (?, ?, ?, 'Find a Tender', 'UK3', ?, 'Energy', 'Mark', '72200000', ?, ?, ?, ?, '{}')",
        (ref, title, buyer, status, now, now, now, now),
    )
    notice_id = cursor.lastrowid
    if rating:
        conn.execute(
            "INSERT INTO phase2_assessments (notice_id, capability_fit_rating, capability_fit_reasoning, "
            "competitor_position_rating, competitor_position_reasoning, right_to_win_rating, "
            "right_to_win_reasoning, overall_rating, overall_reasoning, open_questions, model_used, created_at) "
            "VALUES (?, 'HIGH', 'Strong fit.', 'UNKNOWN', 'Unknown.', 'MED', 'Plausible.', ?, ?, '[]', 'test', ?)",
            (notice_id, rating, f"{rating} recommendation.", now),
        )
    conn.commit()
    return notice_id


def _decision(conn, notice_id, target, actor="Mark", reason="Owner decision"):
    conn.execute(
        "INSERT INTO status_history (notice_id, from_status, to_status, changed_by, changed_at, reason) "
        "VALUES (?, 'AWAITING_PHASE2_APPROVAL', ?, ?, '2026-08-15T10:00:00+00:00', ?)",
        (notice_id, target, actor, reason),
    )
    conn.commit()


def _make_template(path):
    workbook = Workbook()
    workbook.remove(workbook.active)
    summary = workbook.create_sheet("Master Summary")
    summary["B4"] = "=COUNTA(Pass!A3:A1000)"
    for sheet_name in ("Pass", "Flag", "Fail"):
        sheet = workbook.create_sheet(sheet_name)
        sheet.append([sheet_name.upper()])
        sheet.append(list(HEADERS))
    flag = workbook["Flag"]
    flag.append(["N177", "", "Existing Flag", "Existing Buyer"] + [""] * 15)
    font = copy(flag["A3"].font)
    font.bold = True
    flag["A3"].font = font
    workbook.save(path)


def _sheet_titles(workbook, sheet_name):
    return {
        workbook[sheet_name].cell(row, 3).value: workbook[sheet_name].cell(row, 1).value
        for row in range(3, workbook[sheet_name].max_row + 1)
        if workbook[sheet_name].cell(row, 3).value
    }


def test_update_trifork_pipeline_maps_only_owner_phase2_decisions(conn, tmp_path):
    template = tmp_path / "template.xlsx"
    output = tmp_path / "downloads" / "tracker.xlsx"
    _make_template(template)
    original_hash = hashlib.sha256(template.read_bytes()).hexdigest()

    pursue_id = _insert_notice(conn, "REF-PASS", "Approved Pursue", "Buyer A", "ESCALATED_TO_VICTORIA", "PURSUE")
    flag_id = _insert_notice(conn, "REF-FLAG", "Existing Flag", "Existing Buyer", "ESCALATED_TO_VICTORIA", "FLAG")
    reject_id = _insert_notice(conn, "REF-FAIL", "Owner Rejected", "Buyer C", "REJECTED", "DECLINE")
    system_id = _insert_notice(conn, "REF-SYSTEM", "System Rejected", "Buyer D", "REJECTED", "DECLINE")
    _decision(conn, pursue_id, "ESCALATED_TO_VICTORIA")
    _decision(conn, flag_id, "ESCALATED_TO_VICTORIA")
    _decision(conn, reject_id, "REJECTED", reason="No capability fit")
    _decision(conn, system_id, "REJECTED", actor="system_backlog_cleanup")

    result = update_trifork_pipeline(conn, str(template), str(output))

    assert result["Pass"] == 1
    assert result["Flag"] == 1
    assert result["Fail"] == 1
    assert result["total"] == 3
    assert hashlib.sha256(template.read_bytes()).hexdigest() == original_hash

    workbook = load_workbook(output, data_only=False)
    pass_titles = _sheet_titles(workbook, "Pass")
    flag_titles = _sheet_titles(workbook, "Flag")
    fail_titles = _sheet_titles(workbook, "Fail")
    assert pass_titles["Approved Pursue"] == "N178"
    assert flag_titles["Existing Flag"] == "N177"
    assert fail_titles["Owner Rejected"] == "N179"
    assert "System Rejected" not in pass_titles | flag_titles | fail_titles
    assert workbook["Master Summary"]["B4"].value == "=COUNTA(Pass!A3:A1000)"


def test_update_trifork_pipeline_refuses_to_overwrite_template(conn, tmp_path):
    template = tmp_path / "template.xlsx"
    _make_template(template)
    original_hash = hashlib.sha256(template.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="must be different files"):
        update_trifork_pipeline(conn, str(template), str(template))

    assert hashlib.sha256(template.read_bytes()).hexdigest() == original_hash
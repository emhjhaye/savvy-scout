from openpyxl import Workbook

from savvy_scout.models.notice import Notice
from savvy_scout.regression.baseline_compare import (
    compare_against_baseline,
    normalise_outcome,
    read_baseline,
)
from savvy_scout.sources.ocds_parser import ParsedNotice
from savvy_scout.sweep.dedupe import upsert_notice
from savvy_scout.triage.gates import triage_notice


def _make_parsed(ref: str, title: str, buyer: str, text_blob: str, cpv_primary: str | None = None) -> ParsedNotice:
    notice = Notice(
        ref=ref,
        title=title,
        buyer=buyer,
        source="Find a Tender",
        notice_type="UK3",
        uk_stage="UK3",
        raw_json="{}",
        cpv_primary=cpv_primary,
    )
    return ParsedNotice(notice=notice, text_blob=text_blob, tender_status="active")


def test_normalise_outcome():
    assert normalise_outcome("PASS") == "PASS"
    assert normalise_outcome("Fail - out of scope") == "FAIL"
    assert normalise_outcome("FLAG for Victoria") == "FLAG"
    assert normalise_outcome("PASS TO Maddy") == "FLAG"
    assert normalise_outcome("something else entirely") == "OTHER"


def test_read_baseline_and_compare(conn, tmp_path):
    pass_notice = _make_parsed(
        "REF-001", "Real Time Payments Platform", "Some Bank",
        "bespoke build of a real-time payments platform for a bank, a direct award open tender",
        cpv_primary="72200000",
    )
    pass_id = upsert_notice(conn, pass_notice)
    triage_notice(conn, pass_id)

    fail_notice = _make_parsed(
        "REF-002", "Server Hardware Resale", "National Grid",
        "hardware resale of legacy servers for the energy network",
    )
    fail_id = upsert_notice(conn, fail_notice)
    triage_notice(conn, fail_id)

    baseline_path = tmp_path / "baseline.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["Ref #", "Opportunity title", "Triage status"])
    ws.append(["REF-001", "Real Time Payments Platform", "PASS"])
    ws.append(["REF-002", "Server Hardware Resale", "FLAG for Victoria"])  # deliberate disagreement
    ws.append(["REF-999", "Not in our database", "FAIL"])
    wb.save(baseline_path)

    baseline = read_baseline(str(baseline_path))
    assert baseline["REF-001"] == "PASS"

    diff_rows = compare_against_baseline(conn, baseline)
    by_ref = {row["ref"]: row for row in diff_rows}

    assert by_ref["REF-001"]["agree"] is True
    assert by_ref["REF-002"]["agree"] is False
    assert by_ref["REF-002"]["machine_outcome"] == "FAIL"
    assert by_ref["REF-002"]["human_outcome"] == "FLAG"
    assert by_ref["REF-999"]["machine_outcome"] == "NOT IN DATABASE"

from pypdf import PdfReader

from savvy_scout.escalation.brief import build_brief, record_brief
from savvy_scout.models.notice import Notice
from savvy_scout.sources.ocds_parser import ParsedNotice
from savvy_scout.sweep.dedupe import upsert_notice
from savvy_scout.triage.gates import triage_notice
from savvy_scout.triage.scope_read import save_scope_read

SECTION_TITLES = [
    "TRIAGE GATE SUMMARY",
    "SCOUTING ASSESSMENT",
    "WHY THIS IS A HIGH FIT",
    "OPEN BLOCKERS AND RISKS",
    "DIRECT ASKS FOR TRIFORK VIA VICTORIA",
    "DECISION REQUESTED FROM VICTORIA",
]


def _pdf_text(path: str) -> str:
    reader = PdfReader(path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _make_notice(conn):
    # Matches both Fintech ("bank" + "payments platform" coupling) and Energy
    # ("energy" + "smart grid" coupling) -> contested -> Gate 1 FLAG.
    notice = Notice(
        ref="REF-BRIEF-1",
        title="Ambiguous Sector Notice For Brief Test",
        buyer="Some Bank",
        source="Find a Tender",
        notice_type="UK3",
        uk_stage="UK3",
        raw_json="{}",
        notice_url="https://www.find-tender.service.gov.uk/Notice/REF-BRIEF-1",
    )
    parsed = ParsedNotice(
        notice=notice,
        text_blob="real-time payments platform integration with smart grid billing systems "
        "for our energy trading desk",
        tender_status="active",
    )
    notice_id = upsert_notice(conn, parsed)
    triage_notice(conn, notice_id)  # gate1 contested -> FLAG
    return notice_id


def test_build_brief_has_all_sections_and_warning(conn, tmp_path):
    notice_id = _make_notice(conn)
    output_dir = tmp_path / "briefs"
    path = build_brief(conn, notice_id, output_dir=str(output_dir))

    assert path.endswith(".pdf")
    full_text = _pdf_text(path)

    assert "INTERNAL ADDENDUM" in full_text
    assert "NOT FOR CLIENT DISTRIBUTION" in full_text
    assert "AUTO-GENERATED PROVISIONAL DRAFT FOR VALIDATION" in full_text
    assert "Ambiguous Sector Notice For Brief Test" in full_text
    for title in SECTION_TITLES:
        assert title in full_text, f"missing section: {title}"

    # The notice link must never be dropped from the Scouting Assessment section.
    assert "https://www.find-tender.service.gov.uk/Notice/REF-BRIEF-1" in full_text

    # Gate 1's FLAG reason should show up in both the gate summary and risks sections.
    assert "escalate to Victoria" in full_text


def test_build_brief_includes_provisional_label_when_assessment_exists(conn, tmp_path):
    notice_id = _make_notice(conn)
    save_scope_read(
        conn,
        notice_id,
        {
            "capability_fit": {"rating": "LOW", "reasoning": "No clear match."},
            "competitor_position": {"rating": "UNKNOWN", "reasoning": "Not assessed."},
            "right_to_win": {"rating": "LOW", "reasoning": "Weak fit."},
            "overall": {"rating": "DECLINE", "reasoning": "Not worth pursuing."},
            "open_questions": ["Is this really out of sector?"],
        },
    )
    path = build_brief(conn, notice_id, output_dir=str(tmp_path / "briefs"))
    full_text = _pdf_text(path)

    assert "PROVISIONAL, FOR VALIDATION" in full_text
    assert "Is this really out of sector?" in full_text


def test_build_brief_renders_rich_addendum_fields_when_present(conn, tmp_path):
    """Sections C/D/E/F use the richer AI-generated fields (capability
    mapping, structured blockers, asks with reasons, an explicit
    recommendation) when a Phase 2 assessment provides them, matching the
    reference document's exact table shapes -- 2026-08-09."""
    notice_id = _make_notice(conn)
    save_scope_read(
        conn,
        notice_id,
        {
            "capability_fit": {"rating": "HIGH", "reasoning": "Strong engineering fit."},
            "competitor_position": {"rating": "UNKNOWN", "reasoning": "Not assessed."},
            "right_to_win": {"rating": "MED", "reasoning": "Adjacent capability."},
            "overall": {"rating": "PURSUE", "reasoning": "Closest available match."},
            "open_questions": ["Should not appear -- asks take priority."],
            "capability_mapping": [
                {"problem": "Settlement calculations", "capability_mapping": "&Money financial platform"},
            ],
            "blockers": [
                {"blocker": "UK delivery capacity", "assessment": "Approximately 15 UK staff."},
            ],
            "asks": [
                {"ask": "Confirm UK delivery capacity.", "why_it_matters": "Right to win depends on it."},
            ],
            "recommendation": {
                "decision": "PROCEED",
                "immediate_actions": ["Register interest via the buyer's portal."],
                "rationale": "Closest available match to engineering strength.",
            },
        },
    )
    path = build_brief(conn, notice_id, output_dir=str(tmp_path / "briefs"))
    full_text = _pdf_text(path)

    assert "LCCC problem" in full_text
    assert "Trifork capability mapping" in full_text
    assert "&Money financial platform" in full_text
    assert "UK delivery capacity" in full_text
    assert "Confirm UK delivery capacity." in full_text
    assert "Why it matters" in full_text
    assert "Register interest via the buyer" in full_text
    assert "Proceed" in full_text
    # Asks take priority over the plain open_questions fallback.
    assert "Should not appear" not in full_text


def test_record_brief_inserts_row(conn, tmp_path):
    notice_id = _make_notice(conn)
    path = build_brief(conn, notice_id, output_dir=str(tmp_path / "briefs"))
    brief_id = record_brief(conn, notice_id, "gate_flag:gate1", path, "system_triage")

    row = conn.execute("SELECT * FROM escalation_briefs WHERE id = ?", (brief_id,)).fetchone()
    assert row["notice_id"] == notice_id
    assert row["docx_path"] == path
    assert row["emailed_at"] is None

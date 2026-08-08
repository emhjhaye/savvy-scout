from docx import Document

from savvy_scout.escalation.brief import build_brief, record_brief
from savvy_scout.models.notice import Notice
from savvy_scout.sources.ocds_parser import ParsedNotice
from savvy_scout.sweep.dedupe import upsert_notice
from savvy_scout.triage.gates import triage_notice
from savvy_scout.triage.scope_read import save_scope_read

SECTION_TITLES = [
    "Opportunity summary",
    "Buyer",
    "Value",
    "Route to market",
    "Gate outcomes",
    "Provisional ratings with reasoning",
    "Competitor picture",
    "Risks",
    "Open questions",
    "Decision requested",
]


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


def test_build_brief_has_all_ten_sections_and_warning(conn, tmp_path):
    notice_id = _make_notice(conn)
    output_dir = tmp_path / "briefs"
    path = build_brief(conn, notice_id, output_dir=str(output_dir))

    doc = Document(path)
    full_text = "\n".join(p.text for p in doc.paragraphs)

    assert "AUTO-GENERATED PROVISIONAL DRAFT FOR VALIDATION" in full_text
    assert "INTERNAL ADDENDUM: Ambiguous Sector Notice For Brief Test" in full_text
    for title in SECTION_TITLES:
        assert title in full_text, f"missing section: {title}"

    # Gate 1's FLAG reason should show up in both the gate outcomes and risks sections
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
    doc = Document(path)
    full_text = "\n".join(p.text for p in doc.paragraphs)

    assert "PROVISIONAL, FOR VALIDATION" in full_text
    assert "Is this really out of sector?" in full_text


def test_record_brief_inserts_row(conn, tmp_path):
    notice_id = _make_notice(conn)
    path = build_brief(conn, notice_id, output_dir=str(tmp_path / "briefs"))
    brief_id = record_brief(conn, notice_id, "gate_flag:gate1", path, "system_triage")

    row = conn.execute("SELECT * FROM escalation_briefs WHERE id = ?", (brief_id,)).fetchone()
    assert row["notice_id"] == notice_id
    assert row["docx_path"] == path
    assert row["emailed_at"] is None

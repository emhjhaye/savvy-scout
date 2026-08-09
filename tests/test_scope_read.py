import json
from types import SimpleNamespace

import pytest

from savvy_scout.models.notice import Notice
from savvy_scout.sources.ocds_parser import ParsedNotice
from savvy_scout.sweep.dedupe import upsert_notice
from savvy_scout.triage.gates import triage_notice
from savvy_scout.triage.scope_read import get_capability_profile, run_scope_read, save_scope_read

VALID_ASSESSMENT = {
    "capability_fit": {"rating": "MED", "reasoning": "Data platform work, transferable engineering fit."},
    "competitor_position": {"rating": "UNKNOWN", "reasoning": "No incumbent named in the notice."},
    "right_to_win": {"rating": "LOW", "reasoning": "No UK framework access yet, per the capability gaps."},
    "overall": {"rating": "FLAG", "reasoning": "Worth a look but gaps need addressing."},
    "open_questions": ["Does Trifork have a UK reference for this buyer type?"],
}


class FakeTextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class FakeResponse:
    def __init__(self, content_text, stop_reason="end_turn"):
        self.content = [FakeTextBlock(content_text)]
        self.stop_reason = stop_reason


class FakeMessages:
    def __init__(self, response):
        self._response = response
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return self._response


class FakeClient:
    def __init__(self, response):
        self.messages = FakeMessages(response)


def _make_notice(conn):
    notice = Notice(
        ref="REF-SCOPE-1",
        title="Real Time Payments Platform",
        buyer="Some Bank",
        source="Find a Tender",
        notice_type="UK3",
        uk_stage="UK3",
        raw_json="{}",
        cpv_primary="72200000",
    )
    parsed = ParsedNotice(
        notice=notice,
        text_blob="bespoke build of a real-time payments platform, a direct award open tender",
        tender_status="active",
    )
    notice_id = upsert_notice(conn, parsed)
    triage_notice(conn, notice_id)
    return notice_id


def test_get_capability_profile_returns_seeded_text(conn):
    profile = get_capability_profile(conn)
    assert "Erlang" in profile
    assert "capability gaps" in profile.lower()


def test_run_scope_read_parses_structured_output(conn):
    notice_id = _make_notice(conn)
    notice_row = conn.execute("SELECT * FROM notices WHERE id = ?", (notice_id,)).fetchone()

    client = FakeClient(FakeResponse(json.dumps(VALID_ASSESSMENT)))
    assessment = run_scope_read(client, conn, notice_row)

    assert assessment == VALID_ASSESSMENT
    # capability profile should be cached in the system block, not the user message
    system_blocks = client.messages.last_kwargs["system"]
    assert any("cache_control" in block for block in system_blocks)
    assert client.messages.last_kwargs["model"] == "claude-sonnet-5"


def test_run_scope_read_raises_on_refusal(conn):
    notice_id = _make_notice(conn)
    notice_row = conn.execute("SELECT * FROM notices WHERE id = ?", (notice_id,)).fetchone()

    client = FakeClient(FakeResponse("", stop_reason="refusal"))
    with pytest.raises(RuntimeError):
        run_scope_read(client, conn, notice_row)


def test_save_scope_read_persists_all_fields(conn):
    notice_id = _make_notice(conn)
    save_scope_read(conn, notice_id, VALID_ASSESSMENT)

    row = conn.execute(
        "SELECT * FROM phase2_assessments WHERE notice_id = ? ORDER BY id DESC LIMIT 1", (notice_id,)
    ).fetchone()
    assert row["capability_fit_rating"] == "MED"
    assert row["overall_rating"] == "FLAG"
    assert json.loads(row["open_questions"]) == VALID_ASSESSMENT["open_questions"]
    # Internal Addendum sections C-F fields are optional -- absent here, so
    # they persist as NULL rather than raising.
    assert row["capability_mapping"] is None
    assert row["blockers"] is None
    assert row["asks"] is None
    assert row["recommendation"] is None


def test_save_scope_read_persists_internal_addendum_fields_when_present(conn):
    notice_id = _make_notice(conn)
    assessment = {
        **VALID_ASSESSMENT,
        "capability_mapping": [{"problem": "Real-time payments", "capability_mapping": "&Money"}],
        "blockers": [{"blocker": "No UK framework access", "assessment": "Hard block if required."}],
        "asks": [{"ask": "Confirm delivery capacity", "why_it_matters": "Right to win depends on it."}],
        "recommendation": {
            "decision": "PROCEED",
            "immediate_actions": ["Register interest via the buyer's portal."],
            "rationale": "Closest available match to engineering strength.",
        },
    }
    save_scope_read(conn, notice_id, assessment)

    row = conn.execute(
        "SELECT * FROM phase2_assessments WHERE notice_id = ? ORDER BY id DESC LIMIT 1", (notice_id,)
    ).fetchone()
    assert json.loads(row["capability_mapping"]) == assessment["capability_mapping"]
    assert json.loads(row["blockers"]) == assessment["blockers"]
    assert json.loads(row["asks"]) == assessment["asks"]
    assert json.loads(row["recommendation"]) == assessment["recommendation"]

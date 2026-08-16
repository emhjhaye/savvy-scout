import json
from datetime import datetime, timezone

from savvy_scout.escalation.context import MISSING, build_context


def _notice(conn, ref, with_details=True):
    now = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        "INSERT INTO notices (ref, title, buyer, source, uk_stage, status, sector, owner, "
        "indicative_value, cpv_primary, deadline, procurement_method_details, notice_url, "
        "text_blob, first_seen_at, last_swept_at, created_at, updated_at, raw_json) "
        "VALUES (?, 'Digital platform', 'Some Buyer', 'Find a Tender', 'UK3', "
        "'ESCALATED_TO_VICTORIA', 'Fintech', 'Mark', ?, '72200000', ?, ?, ?, ?, ?, ?, ?, ?, '{}')",
        (
            ref,
            "GBP 125000" if with_details else None,
            "2026-08-20T12:00:00+00:00" if with_details else None,
            "Open procedure" if with_details else None,
            "https://example.test/notice" if with_details else None,
            "Full source requirement text" if with_details else "",
            now, now, now, now,
        ),
    )
    notice_id = cursor.lastrowid
    conn.execute(
        "INSERT INTO status_history (notice_id, from_status, to_status, changed_by, changed_at, reason) "
        "VALUES (?, 'AWAITING_PHASE2_APPROVAL', 'ESCALATED_TO_VICTORIA', 'Mark', ?, 'Recommend escalation')",
        (notice_id, now),
    )
    run = conn.execute(
        "INSERT INTO triage_runs (notice_id, headline_gate, headline_outcome, headline_reason, evaluated_at) "
        "VALUES (?, 'gate1', 'FLAG', 'Needs review', ?)",
        (notice_id, now),
    ).lastrowid
    conn.execute(
        "INSERT INTO gate_results (triage_run_id, notice_id, gate_number, gate_name, outcome, reason, evaluated_at) "
        "VALUES (?, ?, 'gate1', 'Buyer in scope', 'FLAG', 'Boundary review required', ?)",
        (run, notice_id, now),
    )
    conn.commit()
    return notice_id


def test_build_context_with_full_ai_read(conn):
    notice_id = _notice(conn, "CTX-FULL")
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO phase2_assessments (notice_id, capability_fit_rating, capability_fit_reasoning, "
        "competitor_position_rating, competitor_position_reasoning, right_to_win_rating, "
        "right_to_win_reasoning, overall_rating, overall_reasoning, open_questions, blockers, asks, "
        "recommendation, model_used, created_at) VALUES (?, 'HIGH', 'Strong fit', 'UNKNOWN', "
        "'No incumbent data', 'MED', 'Credible route', 'FLAG', 'Review with Victoria', ?, ?, ?, ?, 'test', ?)",
        (
            notice_id,
            json.dumps(["Confirm delivery capacity"]),
            json.dumps([{"blocker": "Reference gap", "assessment": "Needs evidence"}]),
            json.dumps([{"ask": "Confirm appetite", "why_it_matters": "Controls next step"}]),
            json.dumps({"decision": "PROCEED", "rationale": "Good fit", "immediate_actions": []}),
            now,
        ),
    )
    conn.commit()

    context = build_context(conn, notice_id)

    assert context["notice_reference"] == "CTX-FULL"
    assert context["value_estimate"] == "125000"
    assert context["currency"] == "GBP"
    assert context["stage"] == "Escalated"
    assert context["ai_read"]["overall"] == "FLAG"
    assert context["direct_asks"][0]["ask"] == "Confirm appetite"
    assert context["urgency"] in ("🔴 URGENT", "🟡 Approaching", "🟢 Open")


def test_build_context_without_ai_read_uses_missing_markers(conn):
    notice_id = _notice(conn, "CTX-NULL", with_details=False)

    context = build_context(conn, notice_id)

    assert context["value_estimate"] == MISSING
    assert context["currency"] == MISSING
    assert context["submission_deadline"] == MISSING
    assert context["route_to_market"] == MISSING
    assert context["ai_read"]["overall"] == MISSING
    assert context["ai_read"]["status"] == "No AI read on file"
"""Phase 2 AI scope reads (SPEC.md B2). On Phase 1 approval, calls the Claude
API with the full notice text and the Trifork capability profile from config,
producing a structured provisional assessment. Single call, structured
output (not tool-use or an agentic loop): this is extraction/judgement
against one document, not multi-step work.

Model: claude-sonnet-5, per your cost/quality call (near-Opus quality on this
kind of structured judgement task, at roughly half the per-notice cost of
Opus 4.8, since this runs on every Phase 1 approval).

The "PROVISIONAL, FOR VALIDATION" label is applied by the application at
display/export time (dashboard templates, escalation brief), never trusted
from the model's own output, per SPEC.md non-negotiable 5."""

import json
import sqlite3
from datetime import datetime, timezone

import anthropic

MODEL = "claude-sonnet-5"
OPENAI_MODEL = "gpt-4o"

SCOPE_READ_SCHEMA = {
    "type": "object",
    "properties": {
        "capability_fit": {
            "type": "object",
            "properties": {
                "rating": {"type": "string", "enum": ["HIGH", "MED", "LOW"]},
                "reasoning": {"type": "string"},
            },
            "required": ["rating", "reasoning"],
            "additionalProperties": False,
        },
        "competitor_position": {
            "type": "object",
            "properties": {
                "rating": {"type": "string", "enum": ["STRONG", "CONTESTED", "WEAK", "UNKNOWN"]},
                "reasoning": {"type": "string"},
            },
            "required": ["rating", "reasoning"],
            "additionalProperties": False,
        },
        "right_to_win": {
            "type": "object",
            "properties": {
                "rating": {"type": "string", "enum": ["HIGH", "MED", "LOW"]},
                "reasoning": {"type": "string"},
            },
            "required": ["rating", "reasoning"],
            "additionalProperties": False,
        },
        "overall": {
            "type": "object",
            "properties": {
                "rating": {"type": "string", "enum": ["PURSUE", "FLAG", "DECLINE"]},
                "reasoning": {"type": "string"},
            },
            "required": ["rating", "reasoning"],
            "additionalProperties": False,
        },
        "open_questions": {"type": "array", "items": {"type": "string"}},
        # Internal Addendum Section C ("Why this is a high fit"): each
        # buyer-side problem paired with the specific Trifork capability/case
        # study that maps to it -- name real case studies from the profile
        # (ALai, &Money, Nordjyllandsfonden, AI Mail Assist, etc.), never a
        # generic capability-area label alone.
        "capability_mapping": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "problem": {"type": "string"},
                    "capability_mapping": {"type": "string"},
                },
                "required": ["problem", "capability_mapping"],
                "additionalProperties": False,
            },
        },
        # Where UK-newness genuinely matters to winning (reference-building,
        # partnering options, presenting European proof points to a UK
        # buyer) -- rendered as its own Internal Addendum section, between
        # capability mapping and blockers. NEVER treated as a blocker or
        # used to lower a rating; see rule 5 and rule 2's exclusion list.
        "positioning_points": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "point": {"type": "string"},
                    "how_to_address": {"type": "string"},
                },
                "required": ["point", "how_to_address"],
                "additionalProperties": False,
            },
        },
        # Section D blockers: ONLY three things, per the Trifork scouting
        # skill v2, Rule 1.1 (11 August 2026, Victoria Milan): wrong type of
        # work, a NAMED framework call-off Trifork is not a member of, or a
        # closed/awarded window. Nothing else counts, including a required
        # product Trifork lacks or a pass/fail certification -- narrower
        # than earlier drafts of this rule.
        # Do NOT include: UK track record, UK references, delivery capacity, staff
        # scale, turnover, or unconfirmed security clearance. Per Victoria Milan's
        # ruling of 11 August 2026 those are positioning points, not blockers.
        # An empty blockers array is a valid result.
        "blockers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "blocker": {"type": "string"},
                    "assessment": {"type": "string"},
                },
                "required": ["blocker", "assessment"],
                "additionalProperties": False,
            },
        },
        # Section E: each open question paired with why it matters to the
        # decision, not just a bare list.
        "asks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ask": {"type": "string"},
                    "why_it_matters": {"type": "string"},
                },
                "required": ["ask", "why_it_matters"],
                "additionalProperties": False,
            },
        },
        # Section F: an explicit recommendation with concrete next actions,
        # not just a rating.
        "recommendation": {
            "type": "object",
            "properties": {
                "decision": {"type": "string", "enum": ["PROCEED", "DO_NOT_PROCEED", "PARK_FOR_MORE_INFO"]},
                "immediate_actions": {"type": "array", "items": {"type": "string"}},
                "rationale": {"type": "string"},
            },
            "required": ["decision", "immediate_actions", "rationale"],
            "additionalProperties": False,
        },
    },
    "required": [
        "capability_fit", "competitor_position", "right_to_win", "overall", "open_questions",
        "capability_mapping", "positioning_points", "blockers", "asks", "recommendation",
    ],
    "additionalProperties": False,
}

SYSTEM_INSTRUCTIONS = """You are assisting Bid Savvy Solutions Ltd's Phase 2 scoping for Trifork UK
(Erlang Solutions Ltd). You will be given a UK public procurement notice's full text, its Phase 1
gate results, and Trifork's capability profile. Produce a structured provisional assessment only.

Context to hold throughout: Trifork is new to the UK market. Bid Savvy was engaged specifically to
build Trifork's UK presence from a standing start. Trifork having no UK track record is the premise
of the engagement, not a finding against an opportunity.

Rules:

1. Never invent a figure, contact, deadline or fact not present in the notice text given to you.
   Where a field is absent, say UNVERIFIED.

2. Rate capability_fit on engineering fit between the requirement and Trifork's capability. Do NOT
   reduce any rating because Trifork is new to the UK. The following must never lower
   capability_fit, right_to_win or the recommendation, and must never appear in blockers:
   - no UK delivery reference, no UK public sector reference, no sector reference
   - UK security clearance population not confirmed
   - absence of UK framework access in general, where the notice names no specific framework
     call-off
   - company size, staff count, turnover or scale
   - no prior relationship with this buyer
   Where any of these genuinely matters to winning, put it in positioning_points, never in
   blockers.

3. capability_fit uses the solution-open test. Cite the notice wording that drives the rating.
   HIGH: the notice leaves solution, vendor and delivery approach genuinely open, and the
   requirement maps to Trifork build capability.
   MED: real build content is present but so are packaged-product signals, for example a
   48xxxxxx CPV, "procure and implement", "provide, implement and support", a supplier
   demonstration stage, a licence-based user model, or language about evaluating what the market
   already offers. State both readings rather than averaging them into one claim.
   LOW: the notice contains too little to assess, or nothing maps.

4. blockers: only three things count as a blocker. Nothing else, ever:
   - wrong type of work: the buyer wants hardware, a packaged product, resale, or a managed
     service on a system Trifork did not build
   - a NAMED framework call-off Trifork is not a member of
   - a closed or awarded window
   If none of these apply, return an empty list. Do not manufacture blockers to appear thorough,
   and do not add a required product, a certification, or unpublished requirements as a blocker --
   those are not one of the three. An empty blockers list is a valid and useful result.

5. positioning_points: what a bid writer must handle to win. This is where UK-newness belongs:
   reference-building, partnering options, and how to present European proof points to a UK
   buyer. Frame each as something to address, never as a reason for doubt.

6. capability_mapping: pair each real buyer-side requirement stated in the notice with the
   SPECIFIC named Trifork case study or product that maps to it. Name the actual case study:
   ALai, &Money, Nordjyllandsfonden, AI Mail Assist; or the actual product: Corax (AI analytics
   and decision support, clinical and AI data), Tiris Messenger (secure operational and
   safety-critical messaging), iFly4 (airline operations), Trifork PIM (planning, optimisation,
   scenario analysis), LOFTHome, Synq. Never a generic label alone. If nothing in the profile
   genuinely maps to a requirement, say so plainly in that row rather than stretching a weak
   analogy.

7. competitor_position: assess only from what the notice reveals. Use UNKNOWN where no incumbent
   or competitive field is identifiable. Do not assume a strong competitive field exists in the
   absence of evidence.

8. right_to_win: base this on the type-of-work question, whether a named framework blocks
   access, and whether the requirement matches Trifork capability. Do not reduce it for UK
   newness.

9. open_questions: genuinely unresolved matters, chiefly whether the requirement is a build or a
   product purchase where the notice does not settle it. Not rhetorical questions.

10. asks: concrete questions FOR Trifork, routed via Victoria, each paired with why it matters to
    the decision.

11. recommendation:
    PROCEED where the type of work fits Trifork capability and the window is open.
    PARK_FOR_MORE_INFO where the notice is genuinely too early-stage or too thin to determine the
    type of work.
    DO_NOT_PROCEED only where the type of work is definitively wrong, a named framework blocks
    access, or the window is closed.
    Never recommend against, and never hedge, on the basis of UK newness, company size,
    references or clearance. Do not use the phrases "suggests reluctance", "may be at a
    disadvantage", "could weaken Trifork's bid", or any similar formulation where the stated
    reason is track record, size, references or clearance.

12. immediate_actions: concrete next steps with owners and dates where known, not vague
    encouragement.

This is a provisional, machine-generated read for a human to validate, not a bid decision."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_capability_profile(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        "SELECT profile_text FROM config_capability_profile ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not row:
        raise RuntimeError("config_capability_profile is empty; run db init/seed first")
    return row["profile_text"]


def _build_notice_context(conn: sqlite3.Connection, notice_row: sqlite3.Row) -> str:
    gate_rows = conn.execute(
        "SELECT gate_name, outcome, reason FROM gate_results WHERE notice_id = ? "
        "ORDER BY id DESC LIMIT 6",
        (notice_row["id"],),
    ).fetchall()
    gate_summary = "\n".join(f"- {g['gate_name']}: {g['outcome']} ({g['reason']})" for g in gate_rows)

    return (
        f"Notice reference: {notice_row['ref']}\n"
        f"Title: {notice_row['title']}\n"
        f"Buyer: {notice_row['buyer'] or 'UNVERIFIED'}\n"
        f"Sector: {notice_row['sector'] or 'UNVERIFIED'}\n"
        f"Indicative value: {notice_row['indicative_value'] or 'UNVERIFIED'}\n"
        f"UK stage: {notice_row['uk_stage']}\n\n"
        f"Phase 1 gate results:\n{gate_summary}\n\n"
        f"Full notice text:\n{notice_row['text_blob']}"
    )


def run_scope_read(
    client: anthropic.Anthropic, conn: sqlite3.Connection, notice_row: sqlite3.Row
) -> dict:
    """Calls Claude Sonnet 5 with structured output and returns the parsed
    assessment dict. Raises RuntimeError if the model refuses."""
    capability_profile = get_capability_profile(conn)
    notice_context = _build_notice_context(conn, notice_row)

    response = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        system=[
            {"type": "text", "text": SYSTEM_INSTRUCTIONS},
            {
                "type": "text",
                "text": f"Trifork capability profile:\n\n{capability_profile}",
                "cache_control": {"type": "ephemeral"},
            },
        ],
        messages=[{"role": "user", "content": notice_context}],
        output_config={"format": {"type": "json_schema", "schema": SCOPE_READ_SCHEMA}},
    )

    if response.stop_reason == "refusal":
        raise RuntimeError(
            f"Claude declined the scope read for notice {notice_row['ref']}; "
            "route to the owner for a manual Phase 2 read."
        )

    text = next(block.text for block in response.content if block.type == "text")
    return json.loads(text)


def run_scope_read_openai(client, conn: sqlite3.Connection, notice_row: sqlite3.Row) -> dict:
    """Same scope read as run_scope_read, against OpenAI instead of Claude
    (2026-07-30, added as a fallback when Anthropic credit ran out). Same
    system instructions, same structured schema -- only the API call shape
    differs, so both providers produce assessments in the same format."""
    capability_profile = get_capability_profile(conn)
    notice_context = _build_notice_context(conn, notice_row)

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        max_tokens=1500,
        messages=[
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {"role": "system", "content": f"Trifork capability profile:\n\n{capability_profile}"},
            {"role": "user", "content": notice_context},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "scope_read", "schema": SCOPE_READ_SCHEMA, "strict": True},
        },
    )

    choice = response.choices[0]
    if choice.finish_reason == "content_filter":
        raise RuntimeError(
            f"OpenAI declined the scope read for notice {notice_row['ref']}; "
            "route to the owner for a manual Phase 2 read."
        )

    return json.loads(choice.message.content)


def get_scope_read_client(settings):
    """Returns (client, scope_read_fn) for whichever provider
    settings.scope_read_provider selects -- the one place that decides which
    API a Phase 2 scope read actually calls. Raises RuntimeError if that
    provider's key isn't configured (callers should check
    settings.scope_read_ready first to show a friendlier UI message)."""
    if settings.scope_read_provider == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("SCOPE_READ_PROVIDER=openai but OPENAI_API_KEY is not set.")
        import openai

        return openai.OpenAI(api_key=settings.openai_api_key), run_scope_read_openai

    if not settings.anthropic_api_key:
        raise RuntimeError("SCOPE_READ_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set.")
    return anthropic.Anthropic(api_key=settings.anthropic_api_key), run_scope_read


def save_scope_read(
    conn: sqlite3.Connection, notice_id: int, assessment: dict, model_used: str = MODEL
) -> int:
    now = _now()
    cursor = conn.execute(
        "INSERT INTO phase2_assessments ("
        "notice_id, capability_fit_rating, capability_fit_reasoning, "
        "competitor_position_rating, competitor_position_reasoning, "
        "right_to_win_rating, right_to_win_reasoning, "
        "overall_rating, overall_reasoning, open_questions, "
        "capability_mapping, positioning_points, blockers, asks, recommendation, model_used, created_at"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            notice_id,
            assessment["capability_fit"]["rating"],
            assessment["capability_fit"]["reasoning"],
            assessment["competitor_position"]["rating"],
            assessment["competitor_position"]["reasoning"],
            assessment["right_to_win"]["rating"],
            assessment["right_to_win"]["reasoning"],
            assessment["overall"]["rating"],
            assessment["overall"]["reasoning"],
            json.dumps(assessment["open_questions"]),
            json.dumps(assessment["capability_mapping"]) if assessment.get("capability_mapping") else None,
            json.dumps(assessment["positioning_points"]) if assessment.get("positioning_points") else None,
            json.dumps(assessment["blockers"]) if assessment.get("blockers") else None,
            json.dumps(assessment["asks"]) if assessment.get("asks") else None,
            json.dumps(assessment["recommendation"]) if assessment.get("recommendation") else None,
            model_used,
            now,
        ),
    )
    conn.commit()
    return cursor.lastrowid

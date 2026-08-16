from pathlib import Path

from docx import Document

from savvy_scout.escalation.context import MISSING, build_context

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "artifacts"


def _set_cell(cell, value):
    text = str(value if value not in (None, "") else MISSING)
    paragraph = cell.paragraphs[0]
    if paragraph.runs:
        paragraph.runs[0].text = text
        for run in paragraph.runs[1:]:
            run.text = ""
    else:
        paragraph.add_run(text)
    for extra in cell.paragraphs[1:]:
        for run in extra.runs:
            run.text = ""


def _set_paragraph(paragraph, value):
    text = str(value if value not in (None, "") else MISSING)
    if paragraph.runs:
        paragraph.runs[0].text = text
        for run in paragraph.runs[1:]:
            run.text = ""
    else:
        paragraph.add_run(text)


def _item_text(value, keys):
    if isinstance(value, dict):
        parts = [str(value[key]) for key in keys if value.get(key)]
        return " — ".join(parts) or MISSING
    return str(value or MISSING)


def _save(document, output_dir, filename):
    output = Path(output_dir) / filename
    output.parent.mkdir(parents=True, exist_ok=True)
    document.save(output)
    return str(output)


def _set_footer(document, context):
    for section in document.sections:
        paragraph = section.footer.paragraphs[0]
        _set_paragraph(
            paragraph,
            f"Smarter Bids. Real Results. | © 2026 Bid Savvy Solutions Ltd | "
            f"{context['notice_reference']} | {context['generated_at'][:19].replace('T', ' ')}",
        )


def build_internal_addendum_docx(conn, notice_id, output_dir):
    context = build_context(conn, notice_id)
    document = Document(TEMPLATE_DIR / "internal_addendum_template.docx")
    tables = document.tables

    _set_cell(
        tables[0].cell(0, 0),
        f"INTERNAL ADDENDUM | NOT FOR CLIENT DISTRIBUTION\n{context['title']}\n"
        f"{context['buyer']} | Reference: {context['notice_reference']} | {context['urgency']}\n"
        f"Prepared by {context['owner_name']}, Bid Savvy Solutions Ltd | {context['generated_at'][:10]}",
    )
    _set_cell(
        tables[1].cell(0, 0),
        "INTERNAL USE ONLY — NOT FOR CLIENT DISTRIBUTION. This document is for Victoria Milan's "
        "GO / NO-GO / Park decision and must not be shared externally.",
    )
    gates = context["gate_outcomes"][:5]
    for index in range(1, 6):
        gate = gates[index - 1] if index <= len(gates) else None
        _set_cell(tables[2].cell(index, 0), f"Gate {index}: {gate['gate_name']}" if gate else f"Gate {index}")
        _set_cell(tables[2].cell(index, 1), f"{gate['result']}. {gate['reason']}" if gate else MISSING)

    metadata = (
        ("Escalated by", context["escalated_by"]),
        ("Escalated at", context["escalated_at"]),
        ("Notice reference", context["notice_reference"]),
        ("Phase 2 status", f"{context['ai_read']['overall']} — PROVISIONAL, FOR VALIDATION"),
        ("Tracker stage", context["stage"]),
        ("Submission deadline", context["submission_deadline"]),
        ("Notice link", context["notice_url"]),
    )
    for row_index, (field, value) in enumerate(metadata, start=1):
        _set_cell(tables[3].cell(row_index, 0), field)
        _set_cell(tables[3].cell(row_index, 1), value)

    reasoning = context["ai_read"].get("per_field_reasoning", {})
    capabilities = (
        ("Capability fit", f"{context['ai_read']['capability_fit']} — {reasoning.get('capability_fit', MISSING)}"),
        ("Competitor position", f"{context['ai_read']['competitor_position']} — {reasoning.get('competitor_position', MISSING)}"),
        ("Right to win", f"{context['ai_read']['right_to_win']} — {reasoning.get('right_to_win', MISSING)}"),
        ("Overall", f"{context['ai_read']['overall']} — {reasoning.get('overall', MISSING)}"),
        ("Validation status", "PROVISIONAL — FOR VALIDATION"),
    )
    _set_cell(tables[4].cell(0, 0), "Capability dimension")
    _set_cell(tables[4].cell(0, 1), "Trifork capability assessment")
    for row_index, (field, value) in enumerate(capabilities, start=1):
        _set_cell(tables[4].cell(row_index, 0), field)
        _set_cell(tables[4].cell(row_index, 1), value)

    risks = context["blockers_risks"] or [MISSING]
    for row_index in range(1, len(tables[5].rows)):
        value = risks[row_index - 1] if row_index <= len(risks) else MISSING
        _set_cell(tables[5].cell(row_index, 0), f"Risk {row_index}")
        _set_cell(tables[5].cell(row_index, 1), _item_text(value, ("blocker", "assessment")))

    asks = context["direct_asks"] or context["ai_read"].get("open_questions", []) or [MISSING]
    for row_index in range(1, len(tables[6].rows)):
        value = asks[row_index - 1] if row_index <= len(asks) else MISSING
        _set_cell(tables[6].cell(row_index, 0), _item_text(value, ("ask", "why_it_matters")))
        _set_cell(tables[6].cell(row_index, 1), "Decision required from Victoria")

    _set_cell(
        tables[7].cell(0, 0),
        f"Decision required: GO, NO-GO or Park for {context['title']} "
        f"(ref {context['notice_reference']}). Owner recommendation: "
        f"{context['recommended_next_action']} — {context['owner_name']}.",
    )
    _set_paragraph(
        document.paragraphs[-1],
        f"Prepared by {context['owner_name']}, Bid Savvy Solutions Ltd | Internal use only | "
        f"Not for client distribution | {context['generated_at'][:10]}",
    )
    _set_footer(document, context)
    safe_ref = context["notice_reference"].replace("/", "-")
    return _save(document, output_dir, f"{safe_ref}_internal_addendum.docx")


def build_capture_brief_docx(conn, notice_id, output_dir):
    context = build_context(conn, notice_id)
    document = Document(TEMPLATE_DIR / "capture_brief_template.docx")
    tables = document.tables
    paragraphs = document.paragraphs

    _set_cell(
        tables[0].cell(0, 0),
        f"CAPTURE BRIEF\n{context['title']}\n{context['buyer']} | Reference: "
        f"{context['notice_reference']} | {context['urgency']}\nPrepared for Victoria Milan | "
        f"{context['generated_at'][:10]}",
    )
    _set_cell(
        tables[1].cell(0, 0),
        f"Why this matters: {context['ai_read'].get('per_field_reasoning', {}).get('overall', MISSING)} "
        "PROVISIONAL — FOR VALIDATION.",
    )
    _set_cell(tables[2].cell(0, 0), f"Submission deadline: {context['submission_deadline']} | {context['urgency']}")

    terms = (
        ("Source", context["source_portal"]),
        ("CPV codes", ", ".join(context["cpv_codes"]) or MISSING),
        ("Route to market", context["route_to_market"]),
        ("Framework status", context["framework_status"]),
        ("Stage", context["stage"]),
    )
    for row_index, (field, value) in enumerate(terms, start=1):
        _set_cell(tables[3].cell(row_index, 0), field)
        _set_cell(tables[3].cell(row_index, 1), value)

    info = (
        ("Contracting authority", context["buyer"]),
        ("Reference", context["notice_reference"]),
        ("Source", context["source_portal"]),
        ("Sector", context["sector"]),
        ("Framework status", context["framework_status"]),
        ("Estimated contract value", f"{context['value_estimate']} {context['currency']}"),
        ("Main CPV codes", ", ".join(context["cpv_codes"]) or MISSING),
        ("Notice link", context["notice_url"]),
        ("Owner", context["owner_name"]),
    )
    for row_index, (field, value) in enumerate(info, start=1):
        _set_cell(tables[4].cell(row_index, 0), field)
        _set_cell(tables[4].cell(row_index, 1), value)

    milestones = (
        ("Notice published", context["published_date"]),
        ("Clarification deadline", context["clarification_deadline"]),
        ("Submission deadline", context["submission_deadline"]),
    )
    for row_index, (field, value) in enumerate(milestones, start=1):
        _set_cell(tables[5].cell(row_index, 0), field)
        _set_cell(tables[5].cell(row_index, 1), value)

    _set_cell(tables[6].cell(1, 0), context["ai_read"]["capability_fit"])
    _set_cell(tables[6].cell(1, 1), context["ai_read"]["competitor_position"])
    _set_cell(tables[6].cell(1, 2), context["ai_read"]["right_to_win"])

    questions = context["ai_read"].get("open_questions", []) or [MISSING]
    for row_index in range(1, len(tables[7].rows)):
        question = questions[row_index - 1] if row_index <= len(questions) else MISSING
        _set_cell(tables[7].cell(row_index, 0), question)
        _set_cell(tables[7].cell(row_index, 1), "Requires validation before decision")

    actions = context["direct_asks"] or [context["recommended_next_action"]]
    for row_index in range(1, len(tables[8].rows)):
        action = actions[row_index - 1] if row_index <= len(actions) else MISSING
        _set_cell(tables[8].cell(row_index, 0), _item_text(action, ("ask", "why_it_matters")))
        _set_cell(tables[8].cell(row_index, 1), context["owner_name"])

    summary = (
        ("Opportunity", context["title"]), ("Buyer", context["buyer"]),
        ("Reference", context["notice_reference"]),
        ("Estimated value", f"{context['value_estimate']} {context['currency']}"),
        ("Route to market", context["route_to_market"]),
        ("Capability fit", context["ai_read"]["capability_fit"]),
        ("Competitive risk", context["ai_read"]["competitor_position"]),
        ("Right to win", context["ai_read"]["right_to_win"]),
        ("Recommended action", context["recommended_next_action"]),
        ("Next deadline", context["submission_deadline"]),
        ("Sources", f"{context['source_portal']} | {context['notice_url']}"),
    )
    for row_index, (field, value) in enumerate(summary, start=1):
        _set_cell(tables[9].cell(row_index, 0), field)
        _set_cell(tables[9].cell(row_index, 1), value)

    replacements = {
        2: context["notice_text"],
        3: context["ai_read"].get("per_field_reasoning", {}).get("overall", MISSING),
        4: "PROVISIONAL — FOR VALIDATION. Owner-reviewed opportunity prepared for Victoria's decision.",
        14: context["notice_text"],
        23: "What the buyer is seeking from this engagement",
        24: context["route_to_market"],
        25: "Engagement model",
        26: context["stage"],
        30: f"Capability fit: {context['ai_read']['capability_fit']}",
        31: context["ai_read"].get("per_field_reasoning", {}).get("capability_fit", MISSING),
        36: f"Competitive risk: {context['ai_read']['competitor_position']}",
        37: context["ai_read"].get("per_field_reasoning", {}).get("competitor_position", MISSING),
        38: f"Right to win: {context['ai_read']['right_to_win']}",
        39: context["ai_read"].get("per_field_reasoning", {}).get("right_to_win", MISSING),
        46: context["recommended_next_action"],
        47: f"Prepared for Victoria's GO / NO-GO / Park decision by {context['owner_name']}.",
        51: f"Prepared by {context['owner_name']}, Bid Savvy Solutions Ltd",
        52: "Confidential | Not for circulation beyond Trifork UK",
    }
    for index, value in replacements.items():
        if index < len(paragraphs):
            _set_paragraph(paragraphs[index], value)
    for index in range(15, 23):
        if index < len(paragraphs):
            _set_paragraph(paragraphs[index], MISSING)
    for index in range(32, 36):
        if index < len(paragraphs):
            _set_paragraph(paragraphs[index], MISSING)

            _set_footer(document, context)

    safe_ref = context["notice_reference"].replace("/", "-")
    return _save(document, output_dir, f"{safe_ref}_capture_brief.docx")

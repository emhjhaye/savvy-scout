import re
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.shared import Pt

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
        extra._element.getparent().remove(extra._element)
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.line_spacing = 1


def _set_paragraph(paragraph, value):
    text = str(value if value not in (None, "") else MISSING)
    if paragraph.runs:
        paragraph.runs[0].text = text
        for run in paragraph.runs[1:]:
            run.text = ""
    else:
        paragraph.add_run(text)


def _remove_paragraph(paragraph):
    paragraph._element.getparent().remove(paragraph._element)


def _set_hyperlink(cell, label, url):
    _set_cell(cell, "")
    paragraph = cell.paragraphs[0]
    for child in list(paragraph._element):
        paragraph._element.remove(child)
    relationship_id = paragraph.part.relate_to(url, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), relationship_id)
    run = OxmlElement("w:r")
    properties = OxmlElement("w:rPr")
    colour = OxmlElement("w:color")
    colour.set(qn("w:val"), "0563C1")
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    properties.extend((colour, underline))
    text = OxmlElement("w:t")
    text.text = label
    run.extend((properties, text))
    hyperlink.append(run)
    paragraph._element.append(hyperlink)


def _item_text(value, keys):
    if isinstance(value, dict):
        parts = [str(value[key]) for key in keys if value.get(key)]
        return " — ".join(parts) or MISSING
    return str(value or MISSING)


def _sentence_case(value):
    text = " ".join(str(value or "").split())
    if not text:
        return ""
    text = text[0].upper() + text[1:]
    replacements = {"orr": "ORR", "uk": "UK", "it": "IT", "ai": "AI", "nhs": "NHS", "microsoft": "Microsoft", "trifork": "Trifork"}
    for source, replacement in replacements.items():
        text = re.sub(rf"\b{source}\b", replacement, text, flags=re.IGNORECASE)
    return text


def _first_sentences(value, count=1, limit=360):
    text = " ".join(str(value or MISSING).split())
    sentences = re.split(r"(?<=[.!?])\s+", text)
    result = " ".join(sentences[:count])
    if len(result) <= limit:
        return result
    return result[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…"


def _scope_points(context):
    title = " ".join(context["title"].casefold().split())
    chunks = []
    for line in str(context["notice_text"]).splitlines():
        cleaned = " ".join(line.split()).strip(" .")
        if not cleaned or cleaned.casefold() == title:
            continue
        if any(cleaned.casefold().startswith(prefix) for prefix in ("below threshold", "open procedure", "it services:")):
            continue
        chunks.extend(re.split(r"(?<=[.!?])\s+|;\s*", cleaned))
    points = []
    for chunk in chunks:
        polished = _sentence_case(chunk.strip(" ."))
        if len(polished) < 25 or polished.casefold() in {point.casefold() for point in points}:
            continue
        points.append(polished + ("" if polished.endswith((".", "?", "!")) else "."))
        if len(points) == 7:
            break
    return points or ["Detailed scope is not stated in the published notice."]


def _format_value(context):
    if context["value_estimate"] == MISSING or str(context["value_estimate"]) in ("0", "0.0"):
        return "Not stated"
    try:
        amount = float(context["value_estimate"])
        formatted = f"{amount:,.0f}" if amount.is_integer() else f"{amount:,.2f}"
    except (TypeError, ValueError):
        return str(context["value_estimate"])
    symbol = {"GBP": "£", "EUR": "€", "USD": "$"}.get(context["currency"])
    return f"{symbol}{formatted}" if symbol else f"{formatted} {context['currency']}"


def _recommended_action(context):
    overall = context["ai_read"]["overall"]
    if overall == "PURSUE":
        return "Recommend GO to capture, subject to Victoria's approval and confirmation of the open risks."
    if overall == "DECLINE":
        return "Recommend NO-GO unless Victoria accepts the identified capability and right-to-win gaps."
    return "Keep at FLAG pending Victoria's GO / NO-GO / Park decision on the identified capability and right-to-win gaps."


def _victoria_asks(context):
    rating = context["ai_read"]
    asks = [
        f"Does Victoria approve pursuing this opportunity with {rating['capability_fit']} capability fit and {rating['right_to_win']} right to win?",
        f"Should the team accept or mitigate the principal capability gap: {_first_sentences(rating.get('per_field_reasoning', {}).get('capability_fit'), 1, 220)}",
    ]
    if context["submission_deadline"] != MISSING:
        asks.append(f"If GO, should capture activity start now against the {context['submission_deadline']} deadline?")
    asks.append("Should this proceed solo, with a delivery partner, or be parked pending stronger evidence?")
    return asks


def _executive_summary(context):
    verb = "is seeking market input on" if context["uk_stage"] == "UK2" else "is procuring"
    scope = _scope_points(context)
    first = f"{context['buyer']} {verb} {context['title']}."
    second = "Published scope: " + " ".join(scope[:3])
    reasoning = context["ai_read"].get("per_field_reasoning", {})
    third = (
        f"Executive view: {context['ai_read']['overall']} (provisional). Capability fit is "
        f"{context['ai_read']['capability_fit']} and right to win is {context['ai_read']['right_to_win']}. "
        f"{_first_sentences(reasoning.get('overall'), 2, 420)}"
    )
    return first, second, third


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
        if field == "Notice link" and context["notice_url"] != MISSING:
            _set_hyperlink(tables[3].cell(row_index, 1), "Open published notice", context["notice_url"])
        else:
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

    asks = _victoria_asks(context)
    for row_index in range(1, len(tables[6].rows)):
        value = asks[row_index - 1] if row_index <= len(asks) else MISSING
        _set_cell(tables[6].cell(row_index, 0), _item_text(value, ("ask", "why_it_matters")))
        _set_cell(tables[6].cell(row_index, 1), "Decision required from Victoria")

    _set_cell(
        tables[7].cell(0, 0),
        f"Decision required: GO, NO-GO or Park for {context['title']} "
        f"(ref {context['notice_reference']}). Owner recommendation: "
        f"{_recommended_action(context)} — {context['owner_name']}.",
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
        f"Why this matters: {_first_sentences(context['ai_read'].get('per_field_reasoning', {}).get('capability_fit'), 2, 420)} "
        f"Decision point: {_recommended_action(context)} PROVISIONAL — FOR VALIDATION.",
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
        ("Estimated contract value", _format_value(context)),
        ("Main CPV codes", ", ".join(context["cpv_codes"]) or MISSING),
        ("Notice link", "Open published notice"),
        ("Owner", context["owner_name"]),
    )
    for row_index, (field, value) in enumerate(info, start=1):
        _set_cell(tables[4].cell(row_index, 0), field)
        if field == "Notice link" and context["notice_url"] != MISSING:
            _set_hyperlink(tables[4].cell(row_index, 1), value, context["notice_url"])
        else:
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

    questions = _victoria_asks(context)
    for row_index in range(1, len(tables[7].rows)):
        question = questions[row_index - 1] if row_index <= len(questions) else MISSING
        _set_cell(tables[7].cell(row_index, 0), question)
        _set_cell(tables[7].cell(row_index, 1), "Requires validation before decision")

    actions = [_recommended_action(context)]
    for row_index in range(1, len(tables[8].rows)):
        action = actions[row_index - 1] if row_index <= len(actions) else MISSING
        _set_cell(tables[8].cell(row_index, 0), _item_text(action, ("ask", "why_it_matters")))
        _set_cell(tables[8].cell(row_index, 1), context["owner_name"])

    summary = (
        ("Opportunity", context["title"]), ("Buyer", context["buyer"]),
        ("Reference", context["notice_reference"]),
        ("Estimated value", _format_value(context)),
        ("Route to market", context["route_to_market"]),
        ("Capability fit", context["ai_read"]["capability_fit"]),
        ("Competitive risk", context["ai_read"]["competitor_position"]),
        ("Right to win", context["ai_read"]["right_to_win"]),
        ("Recommended action", _recommended_action(context)),
        ("Next deadline", context["submission_deadline"]),
        ("Sources", context["source_portal"]),
    )
    for row_index, (field, value) in enumerate(summary, start=1):
        _set_cell(tables[9].cell(row_index, 0), field)
        _set_cell(tables[9].cell(row_index, 1), value)

    executive = _executive_summary(context)
    scope_points = _scope_points(context)
    replacements = {
        2: executive[0],
        3: executive[1],
        4: executive[2] + " PROVISIONAL — FOR VALIDATION.",
        14: "The published notice describes the following scope:",
        23: "What the buyer is seeking from this engagement",
        24: context["route_to_market"] if context["route_to_market"] != MISSING else "Route to market not stated in the notice.",
        25: "Engagement model",
        26: context["stage"],
        30: f"Capability fit: {context['ai_read']['capability_fit']}",
        31: context["ai_read"].get("per_field_reasoning", {}).get("capability_fit", MISSING),
        36: f"Competitive risk: {context['ai_read']['competitor_position']}",
        37: context["ai_read"].get("per_field_reasoning", {}).get("competitor_position", MISSING),
        38: f"Right to win: {context['ai_read']['right_to_win']}",
        39: context["ai_read"].get("per_field_reasoning", {}).get("right_to_win", MISSING),
        46: _recommended_action(context),
        47: f"Prepared for Victoria's GO / NO-GO / Park decision by {context['owner_name']}.",
        51: f"Prepared by {context['owner_name']}, Bid Savvy Solutions Ltd",
        52: "Confidential | Not for circulation beyond Trifork UK",
    }
    for index, value in replacements.items():
        if index < len(paragraphs):
            _set_paragraph(paragraphs[index], value)
    scope_paragraphs = paragraphs[15:23]
    for index, paragraph in enumerate(scope_paragraphs):
        if index < len(scope_points):
            _set_paragraph(paragraph, scope_points[index])
        else:
            _remove_paragraph(paragraph)
    for paragraph in paragraphs[32:36]:
        _remove_paragraph(paragraph)

    _set_footer(document, context)

    safe_ref = context["notice_reference"].replace("/", "-")
    return _save(document, output_dir, f"{safe_ref}_capture_brief.docx")

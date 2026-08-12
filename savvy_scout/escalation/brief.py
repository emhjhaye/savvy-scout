"""Escalation documents (SPEC v1.5 B3).

- Internal Addendum: generated on owner-marked Victoria escalation. PDF,
  branded to match the rest of the app (red #AF1F23 header language),
  table-based sections -- see build_internal_addendum.
- Capture Brief: generated only after Victoria GO (approve). Also PDF,
  same visual language -- see build_capture_brief.

2026-08-09: switched both from python-docx to reportlab-generated PDF
(explicit request -- match a supplied reference document's exact design:
red section-table headers, a bordered "internal use only" callout box,
notice link never dropped). reportlab is pure-Python (no LibreOffice/MS
Word needed), so this works unchanged on Render's Linux container.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape as _xml_escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

GATE_ORDER = ["gate1", "gate2", "gate3", "gate4", "gate5", "filter3"]

# SAVVY_SCOUT_BRIEFS_DIR lets a production deploy (Render's persistent disk,
# e.g. /var/data/briefs) point generated files somewhere that actually
# survives a redeploy -- the default keeps local dev unchanged.
DEFAULT_BRIEFS_DIR = os.environ.get("SAVVY_SCOUT_BRIEFS_DIR", "briefs")

# Same brand red used throughout the dashboard's CSS (base.html --primary).
BRAND_RED = colors.HexColor("#AF1F23")
CALLOUT_BG = colors.HexColor("#EFF6FF")
CALLOUT_BORDER = colors.HexColor("#3B82F6")
ROW_ALT_BG = colors.HexColor("#F9FAFB")
GRID_COLOR = colors.HexColor("#E5E7EB")
MUTED_TEXT = colors.HexColor("#6B7280")
PAGE_WIDTH = 16 * cm


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _esc(value) -> str:
    """Escapes &, < and > in dynamic content (notice/AI text) before it goes
    into a reportlab Paragraph -- Paragraph parses its string as a small XML
    dialect, so an unescaped "&" (e.g. a buyer or case study named "&Money")
    silently corrupts or drops that part of the text instead of raising.
    Never call this on the static markup strings this module writes itself
    (those intentionally use &nbsp;/&middot;/&ldquo;/etc as real entities)."""
    if value is None or value == "":
        return ""
    return _xml_escape(str(value))


def _pdf_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        "BriefBanner", parent=styles["Normal"], fontSize=9, textColor=BRAND_RED,
        fontName="Helvetica-Bold", spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        "BriefTitle", parent=styles["Title"], fontSize=17, alignment=TA_LEFT,
        textColor=colors.HexColor("#111827"), spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        "BriefMeta", parent=styles["Normal"], fontSize=9.5,
        textColor=colors.HexColor("#4B5563"), spaceAfter=2,
    ))
    styles.add(ParagraphStyle(
        "BriefSectionHeading", parent=styles["Heading2"], fontSize=12.5,
        textColor=BRAND_RED, spaceBefore=16, spaceAfter=6,
    ))
    styles.add(ParagraphStyle("BriefCell", parent=styles["Normal"], fontSize=9.5, leading=13))
    styles.add(ParagraphStyle(
        "BriefCellHeader", parent=styles["Normal"], fontSize=9.5, leading=13,
        textColor=colors.white, fontName="Helvetica-Bold",
    ))
    styles.add(ParagraphStyle("BriefFooter", parent=styles["Normal"], fontSize=8, textColor=MUTED_TEXT))
    return styles


def _section_table(col_headers: list[str], rows: list[tuple], col_widths: list[float], styles) -> Table:
    """A section's data table: red header row (brand colour), alternating
    row shading, full grid -- the visual language every section below uses,
    matching the reference document's tables."""
    header = [Paragraph(h, styles["BriefCellHeader"]) for h in col_headers]
    data = [header]
    for row in rows:
        data.append([Paragraph(_esc(cell) or "&mdash;", styles["BriefCell"]) for cell in row])
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_RED),
        ("GRID", (0, 0), (-1, -1), 0.5, GRID_COLOR),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ROW_ALT_BG]),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def _callout_box(text: str, styles) -> Table:
    box = Table([[Paragraph(text, styles["BriefCell"])]], colWidths=[PAGE_WIDTH])
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CALLOUT_BG),
        ("BOX", (0, 0), (-1, -1), 1, CALLOUT_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return box


def _header_block(notice: sqlite3.Row, banner_text: str, styles) -> list:
    meta_bits = [_esc(notice["buyer"]) or "UNVERIFIED", f"Reference: {_esc(notice['ref'])}"]
    if notice["sector"]:
        meta_bits.append(f"Sector: {_esc(notice['sector'])}")
    return [
        Paragraph(banner_text, styles["BriefBanner"]),
        Paragraph(_esc(notice["title"]) or "UNVERIFIED", styles["BriefTitle"]),
        Paragraph(" &middot; ".join(meta_bits), styles["BriefMeta"]),
        Paragraph(
            f"Auto-generated by Savvy Scout &middot; {datetime.now(timezone.utc).strftime('%d %B %Y')}",
            styles["BriefMeta"],
        ),
        Spacer(1, 10),
    ]


def _footer_block(text: str, styles) -> list:
    return [
        Spacer(1, 16),
        HRFlowable(width="100%", color=GRID_COLOR),
        Spacer(1, 6),
        Paragraph(text, styles["BriefFooter"]),
    ]


def _build_pdf(output_path: str, story: list) -> str:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm, leftMargin=1.5 * cm, rightMargin=1.5 * cm,
    )
    doc.build(story)
    return output_path


def _latest_gate_results(conn: sqlite3.Connection, notice_id: int) -> list[sqlite3.Row]:
    run = conn.execute(
        "SELECT id FROM triage_runs WHERE notice_id = ? ORDER BY id DESC LIMIT 1", (notice_id,)
    ).fetchone()
    if not run:
        return []
    rows = conn.execute(
        "SELECT gate_number, gate_name, outcome, reason FROM gate_results WHERE triage_run_id = ?",
        (run["id"],),
    ).fetchall()
    by_gate = {r["gate_number"]: r for r in rows}
    return [by_gate[g] for g in GATE_ORDER if g in by_gate]


def _latest_assessment(conn: sqlite3.Connection, notice_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM phase2_assessments WHERE notice_id = ? ORDER BY id DESC LIMIT 1",
        (notice_id,),
    ).fetchone()


def build_internal_addendum(conn: sqlite3.Connection, notice_id: int, output_dir: str = DEFAULT_BRIEFS_DIR) -> str:
    """Generated the moment a notice is escalated (owner-marked or an
    automatic Gate flag) -- BEFORE Victoria has made any decision. This is
    what she reviews to decide go/no-go/park; the Capture Brief below is a
    different, later document only generated after she says go."""
    notice = conn.execute("SELECT * FROM notices WHERE id = ?", (notice_id,)).fetchone()
    if notice is None:
        raise ValueError(f"No notice with id {notice_id}")

    gate_rows = _latest_gate_results(conn, notice_id)
    assessment = _latest_assessment(conn, notice_id)
    flagged_gates = [g for g in gate_rows if g["outcome"] in ("FLAG", "MAYBE")]

    styles = _pdf_styles()
    story = _header_block(notice, "INTERNAL ADDENDUM &nbsp;|&nbsp; NOT FOR CLIENT DISTRIBUTION", styles)

    story.append(_callout_box(
        "Internal use only. This document is for Victoria Milan's use only. It contains triage gate "
        "outcomes, scouting rationale, open blockers, and direct asks for Trifork. It must not be "
        "shared with Trifork or any external party.",
        styles,
    ))
    story.append(Paragraph(
        "AUTO-GENERATED PROVISIONAL DRAFT FOR VALIDATION. Decision belongs to Victoria Milan, Bid Director.",
        styles["BriefFooter"],
    ))
    story.append(Spacer(1, 14))

    story.append(Paragraph("A. TRIAGE GATE SUMMARY", styles["BriefSectionHeading"]))
    gate_summary_rows = (
        [(f"Gate {GATE_ORDER.index(g['gate_number']) + 1}: {g['gate_name']}", f"{g['outcome']}. {g['reason']}")
         for g in gate_rows]
        or [("Not yet triaged", "")]
    )
    story.append(_section_table(["Gate", "Outcome"], gate_summary_rows, [4 * cm, 12 * cm], styles))

    story.append(Paragraph("B. SCOUTING ASSESSMENT", styles["BriefSectionHeading"]))
    # "Spotted by" / a separately-drafted client brief / an external tracker
    # spreadsheet don't exist as concepts in this app -- sweeping is fully
    # automated (nobody "spots" a notice) and there's no client-brief
    # workflow or external tracker to report status from. Every row below is
    # something Savvy Scout actually tracks; the notice link is deliberately
    # its own row, never dropped -- the actual published notice on its
    # source portal, not just the reference number.
    scouting_rows = [
        ("Pipeline reference", f"SS-{notice['id']}"),
        ("First seen (swept)", (notice["first_seen_at"] or "")[:10] or "UNVERIFIED"),
        ("Published", (notice["published_at"] or "")[:10] or "UNVERIFIED"),
        ("Sector", notice["sector"] or "UNVERIFIED"),
        ("Owner", notice["owner"] or "Unassigned"),
        ("Deadline", (notice["deadline"] or "")[:10] or "UNVERIFIED"),
        ("Notice reference", f"{notice['ref']}, {notice['source']}"),
        ("Notice link", notice["notice_url"] or "Not published by source"),
    ]
    story.append(_section_table(["Field", "Detail"], scouting_rows, [4 * cm, 12 * cm], styles))

    story.append(Paragraph("C. WHY THIS IS A HIGH FIT", styles["BriefSectionHeading"]))
    capability_mapping = json.loads(assessment["capability_mapping"]) if assessment and assessment["capability_mapping"] else None
    if capability_mapping:
        fit_rows = [(row["problem"], row["capability_mapping"]) for row in capability_mapping]
        story.append(_section_table(["LCCC problem", "Trifork capability mapping"], fit_rows, [6 * cm, 10 * cm], styles))
    elif assessment:
        story.append(_section_table(
            ["Dimension", "Assessment"],
            [
                ("Capability fit", f"{assessment['capability_fit_rating']} -- "
                 f"{assessment['capability_fit_reasoning']} (PROVISIONAL, FOR VALIDATION)"),
                ("Right to win", f"{assessment['right_to_win_rating']} -- "
                 f"{assessment['right_to_win_reasoning']} (PROVISIONAL, FOR VALIDATION)"),
            ],
            [4 * cm, 12 * cm], styles,
        ))
    else:
        story.append(Paragraph("Phase 2 scope read has not run yet for this notice.", styles["BriefCell"]))

    # UK-newness (reference-building, partnering, European proof points)
    # lives here, never in blockers below (Victoria Milan's ruling of 11
    # August 2026, corrected into the prompt 2026-08-12). A bid writer
    # genuinely needs this; it just isn't a reason for doubt.
    story.append(Paragraph("D. POSITIONING POINTS", styles["BriefSectionHeading"]))
    positioning_points = (
        json.loads(assessment["positioning_points"]) if assessment and assessment["positioning_points"] else None
    )
    if positioning_points:
        positioning_rows = [(row["point"], row["how_to_address"]) for row in positioning_points]
        story.append(_section_table(["Point", "How to address"], positioning_rows, [6 * cm, 10 * cm], styles))
    else:
        story.append(Paragraph("None recorded.", styles["BriefCell"]))

    story.append(Paragraph("E. OPEN BLOCKERS AND RISKS", styles["BriefSectionHeading"]))
    blockers = json.loads(assessment["blockers"]) if assessment and assessment["blockers"] else None
    if blockers:
        risk_rows = [(row["blocker"], row["assessment"]) for row in blockers]
    else:
        risk_rows = [(g["gate_name"], g["reason"]) for g in flagged_gates] or [("No gate flags recorded", "")]
    story.append(_section_table(["Blocker or risk", "Assessment"], risk_rows, [4 * cm, 12 * cm], styles))

    story.append(Paragraph("F. DIRECT ASKS FOR TRIFORK VIA VICTORIA", styles["BriefSectionHeading"]))
    asks = json.loads(assessment["asks"]) if assessment and assessment["asks"] else None
    if asks:
        ask_rows = [(row["ask"], row["why_it_matters"]) for row in asks]
        story.append(_section_table(["Ask", "Why it matters"], ask_rows, [6 * cm, 10 * cm], styles))
    else:
        open_questions = json.loads(assessment["open_questions"]) if assessment else []
        question_rows = [(q,) for q in open_questions] or [("None recorded.",)]
        story.append(_section_table(["Open question"], question_rows, [16 * cm], styles))

    story.append(Paragraph("G. DECISION REQUESTED FROM VICTORIA", styles["BriefSectionHeading"]))
    recommendation = json.loads(assessment["recommendation"]) if assessment and assessment["recommendation"] else None
    if recommendation:
        actions = "".join(f"({i}) {_esc(a)} " for i, a in enumerate(recommendation["immediate_actions"], start=1))
        decision_text = (
            f"Decision required: does Victoria want to proceed with &ldquo;{_esc(notice['title'])}&rdquo; "
            f"(ref {_esc(notice['ref'])})? Recommendation: {_esc(recommendation['decision'].replace('_', ' ').title())} "
            f"-- {_esc(recommendation['rationale'])} (PROVISIONAL, FOR VALIDATION)."
        )
        if actions.strip():
            decision_text += f" If yes, immediate actions: {actions.strip()}"
    else:
        decision_text = (
            f"Decision required: go, no-go or park for &ldquo;{_esc(notice['title'])}&rdquo; "
            f"(ref {_esc(notice['ref'])})."
        )
    story.append(_callout_box(decision_text, styles))

    story.extend(_footer_block(
        "Auto-generated by Savvy Scout &middot; Internal use only &middot; Not for client distribution",
        styles,
    ))

    safe_ref = notice["ref"].replace("/", "-")
    output_path = str(Path(output_dir) / f"{safe_ref}_internal_addendum.pdf")
    return _build_pdf(output_path, story)


def build_capture_brief(conn: sqlite3.Connection, notice_id: int, output_dir: str = DEFAULT_BRIEFS_DIR) -> str:
    """Generated ONLY after Victoria's GO decision (workflow.approvals.
    victoria_decision, decision='approve') -- never before. Same visual
    language as the Internal Addendum, client-facing content."""
    notice = conn.execute("SELECT * FROM notices WHERE id = ?", (notice_id,)).fetchone()
    if notice is None:
        raise ValueError(f"No notice with id {notice_id}")

    assessment = _latest_assessment(conn, notice_id)
    styles = _pdf_styles()
    story = _header_block(notice, "CAPTURE BRIEF &nbsp;|&nbsp; PREPARED UNDER VICTORIA MILAN, BID DIRECTOR", styles)

    story.append(_section_table(
        ["Field", "Detail"],
        [
            ("Reference", notice["ref"]),
            ("Buyer", notice["buyer"] or "UNVERIFIED"),
            ("Value", (notice["indicative_value"] or "UNVERIFIED")
             + (f" (inc. VAT: {notice['value_amount_gross']})" if notice["value_amount_gross"] else "")),
            ("Above threshold", ("Yes" if notice["above_threshold"] else "No")
             if notice["above_threshold"] is not None else "UNVERIFIED"),
            ("Category", notice["main_procurement_category"] or ""),
            ("Notice link", notice["notice_url"] or "Not published by source"),
        ],
        [4 * cm, 12 * cm], styles,
    ))

    story.append(Paragraph("PROCUREMENT MECHANICS", styles["BriefSectionHeading"]))
    story.append(_section_table(
        ["Field", "Detail"],
        [
            ("Source", notice["source"]),
            ("UK stage", notice["uk_stage"]),
            ("Procedure", notice["procurement_method"] or "UNVERIFIED"),
            ("Procedure details", notice["procurement_method_details"] or ""),
            ("Procedure features", notice["procedure_features"] or ""),
        ],
        [4 * cm, 12 * cm], styles,
    ))

    story.append(Paragraph("PROCUREMENT TIMETABLE", styles["BriefSectionHeading"]))
    contract_range = (
        f"{notice['contract_start_date'] or 'UNVERIFIED'} to {notice['contract_end_date'] or 'UNVERIFIED'}"
        + (f" (max extent {notice['contract_max_extent_date']})" if notice["contract_max_extent_date"] else "")
    )
    story.append(_section_table(
        ["Field", "Detail"],
        [
            ("Enquiry period end", notice["enquiry_period_end"] or ""),
            ("Deadline", notice["deadline"] or "UNVERIFIED"),
            ("Award decision (est.)", notice["award_period_end"] or ""),
            ("Contract", contract_range),
            ("Renewal", notice["renewal_description"] or ""),
        ],
        [4 * cm, 12 * cm], styles,
    ))

    story.append(Paragraph("AWARD CRITERIA", styles["BriefSectionHeading"]))
    story.append(Paragraph(_esc(notice["award_criteria_summary"]) or "Not stated.", styles["BriefCell"]))

    story.append(Paragraph("SUBMISSION DETAILS", styles["BriefSectionHeading"]))
    story.append(_section_table(
        ["Field", "Detail"],
        [
            ("Method", notice["submission_method_details"] or "Not stated -- see original notice."),
            ("Electronic submission", notice["electronic_submission_policy"] or ""),
            ("Languages", notice["submission_languages"] or ""),
        ],
        [4 * cm, 12 * cm], styles,
    ))

    story.append(Paragraph("SCOPE OF REQUIREMENT", styles["BriefSectionHeading"]))
    story.append(Paragraph(_esc((notice["text_blob"] or "UNVERIFIED")[:1200]), styles["BriefCell"]))

    story.append(Paragraph("CONTACTS AND BUYER DETAILS", styles["BriefSectionHeading"]))
    story.append(_section_table(
        ["Field", "Detail"],
        [
            ("Contracting authority", notice["buyer_address"] or "UNVERIFIED"),
            ("PPON", notice["buyer_ppon"] or ""),
            ("Contact", notice["buyer_contact_email"] or ""),
            ("Website", notice["buyer_website"] or ""),
            ("Organisation type", notice["buyer_org_type"] or ""),
            ("Incumbent supplier", notice["supplier_name"] or ""),
            ("Conflicts assessment", notice["conflicts_assessment"] or ""),
        ],
        [4 * cm, 12 * cm], styles,
    ))

    story.append(Paragraph("CAPABILITY AND FIT ASSESSMENT", styles["BriefSectionHeading"]))
    fit_text = (
        f"{_esc(assessment['overall_rating'])} -- {_esc(assessment['overall_reasoning'])}"
        if assessment else "PROVISIONAL, FOR VALIDATION -- no assessment available."
    )
    story.append(Paragraph(fit_text, styles["BriefCell"]))

    story.append(Paragraph("DECISION FRAMEWORK", styles["BriefSectionHeading"]))
    story.append(_callout_box(
        "Proceed based on Victoria's GO decision and owner readiness. Confirm route to market, "
        "timeline and clarifications before submission.",
        styles,
    ))

    story.extend(_footer_block(
        "Auto-generated by Savvy Scout &middot; Generated post-GO per v1.5 policy &middot; Client-facing draft",
        styles,
    ))

    safe_ref = notice["ref"].replace("/", "-")
    output_path = str(Path(output_dir) / f"{safe_ref}_capture_brief.pdf")
    return _build_pdf(output_path, story)


def build_brief(conn: sqlite3.Connection, notice_id: int, output_dir: str = DEFAULT_BRIEFS_DIR) -> str:
    # Backward-compatible alias used by older callers.
    return build_internal_addendum(conn, notice_id, output_dir)


def record_brief(
    conn: sqlite3.Connection,
    notice_id: int,
    trigger_reason: str,
    docx_path: str,
    created_by: str,
    brief_type: str = "INTERNAL_ADDENDUM",
) -> int:
    now = _now()
    cursor = conn.execute(
        "INSERT INTO escalation_briefs (notice_id, trigger_reason, docx_path, created_by, created_at, brief_type) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (notice_id, trigger_reason, docx_path, created_by, now, brief_type),
    )
    conn.commit()
    return cursor.lastrowid


def mark_emailed(conn: sqlite3.Connection, brief_id: int, recipient: str) -> None:
    conn.execute(
        "UPDATE escalation_briefs SET emailed_to = ?, emailed_at = ? WHERE id = ?",
        (recipient, _now(), brief_id),
    )
    conn.commit()

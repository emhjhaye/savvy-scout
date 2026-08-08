"""Phase 1 triage gates (SPEC.md A3), five gates plus Filter 3, built on the
decisions you made on the flagged disagreements:

- Gate 1 owner map: Energy = Mark. Ambiguous or contested sector = FLAG to
  Victoria (Maddy routing from the references is retired, Maddy left the
  team 2026-07-15). Rail and Transport = Mark. A bare industry keyword with
  no product/capability coupling term (2026-07-21 update) is out of sector
  and FAILs, no owner assigned -- superseding the earlier "never fail if
  unsure" FLAG-to-Victoria call for this specific case. Still gets a human
  double-check like every other FAIL (2026-07-28 clarification: the gates
  can misclassify, so no FAIL skips owner review, this one included).
- Gate 2: platform/digital/data are generic and require a sector or
  capability/product coupling term to PASS; uncoupled = FLAG, not PASS.
  Fail list unchanged.
- Gate 5: judged on the primary CPV code. Additional CPV codes are recorded
  for reference and noted only when they conflict with the primary outcome.
- All gates always run and record a result; no short-circuit on first FAIL.
  The first non-PASS gate result, in gate order, is the headline outcome.
- Filter 3 (scale/SI-prime dominance) is a separately agreed rule (15 June
  2026), distinct from the "no minimum value floor" non-negotiable, and is
  config-driven with an enabled/disabled toggle.
"""

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone

from savvy_scout.logging_util import log_audit, log_status_change
from savvy_scout.models.notice import Status, validate_transition
from savvy_scout.triage.sector_classifier import classify_sector, is_contested, uncoupled_candidate_sectors

GATE_ORDER = ["gate1", "gate2", "gate3", "gate4", "gate5", "filter3"]

GATE_NAMES = {
    "gate1": "Buyer sector and owner",
    "gate2": "Type of work (with CPV evidence)",
    "gate3": "Notice stage",
    "gate4": "Window",
    "gate5": "Framework status",
    "filter3": "Scale and incumbents",
}

AIRPORT_TERMS = [
    "airport",
    "air traffic control",
    "national air traffic",
    "defence aviation",
    "military aviation",
    "raf base",
]


@dataclass
class GateResult:
    outcome: str
    reason: str
    extra: dict = field(default_factory=dict)


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _extract_numeric_value(indicative_value: str | None) -> float | None:
    if not indicative_value:
        return None
    numbers = re.findall(r"[\d.]+", indicative_value.replace(",", ""))
    if not numbers:
        return None
    return max(float(n) for n in numbers)


def _is_airport_or_defence_aviation(buyer: str | None, text_blob: str) -> bool:
    haystack = f"{(buyer or '').lower()}\n{text_blob.lower()}"
    return any(term in haystack for term in AIRPORT_TERMS)


def gate1_sector_owner(conn: sqlite3.Connection, buyer: str | None, text_blob: str) -> GateResult:
    if _is_airport_or_defence_aviation(buyer, text_blob):
        return GateResult(
            "FAIL",
            "Airport-side, air traffic control or defence aviation; Trifork's aviation "
            "scope is airlines only.",
        )

    if is_contested(conn, buyer, text_blob):
        return GateResult(
            "FLAG",
            "Buyer/notice text matches more than one configured sector's keywords; "
            "ambiguous or contested, escalate to Victoria.",
        )

    sector = classify_sector(conn, buyer, text_blob)
    if sector is None:
        candidates = uncoupled_candidate_sectors(conn, buyer, text_blob)
        if candidates:
            return GateResult(
                "FAIL",
                f"Buyer/notice mentions the {', '.join(sorted(candidates))} industry, but no "
                "digital/software product or capability signal was found alongside it; "
                "out of sector. Still routed to TO_REVIEW like any other FAIL, since this "
                "gate's keyword match can be wrong -- see triage_notice.",
            )
        return GateResult(
            "FAIL",
            "No configured sector keyword matched this buyer or notice text; "
            "obviously out of scope (none of the four confirmed sectors, NHS/healthcare, "
            "or Central/Local Government).",
        )

    owner_row = conn.execute(
        "SELECT owner FROM config_owner_map WHERE sector = ?", (sector,)
    ).fetchone()
    owner = owner_row["owner"] if owner_row else None
    if not owner:
        return GateResult(
            "FLAG",
            f"Sector '{sector}' matched but has no owner configured; escalate to Victoria.",
        )

    return GateResult(
        "PASS",
        f"Sector: {sector}. Owner: {owner}.",
        extra={"sector": sector, "owner": owner},
    )


def _sector_cpv_scope(conn: sqlite3.Connection, sector: str | None) -> list[str] | None:
    """Returns the allowed CPV prefixes for a sector with an enabled
    config_sector_cpv_scope row, or None if that sector isn't scoped (should
    fall back to the global config_cpv_lists lookup)."""
    if not sector:
        return None
    row = conn.execute(
        "SELECT allowed_cpv_prefixes FROM config_sector_cpv_scope WHERE sector = ? AND enabled = 1",
        (sector,),
    ).fetchone()
    if not row:
        return None
    return json.loads(row["allowed_cpv_prefixes"])


def gate2_type_of_work(
    conn: sqlite3.Connection,
    text_blob: str,
    cpv_primary: str | None = None,
    cpv_primary_inferred: bool = False,
    cpv_additional: list[str] | None = None,
    sector: str | None = None,
) -> GateResult:
    if cpv_additional is None:
        cpv_additional = []

    terms = conn.execute("SELECT term, category FROM config_gate2_terms").fetchall()

    fail_matches = [t["term"] for t in terms if t["category"] == "fail" and t["term"] in text_blob]
    if fail_matches:
        return GateResult("FAIL", f"Matched fail term(s): {', '.join(fail_matches)}.")

    pass_matches = [
        t["term"] for t in terms if t["category"] == "unconditional_pass" and t["term"] in text_blob
    ]
    base_outcome = "FLAG"
    base_reason = "No Gate 2 keyword matched (pass, fail or generic); type of work unclear, do not rate."

    if pass_matches:
        base_outcome = "PASS"
        base_reason = f"Matched unconditional pass term(s): {', '.join(pass_matches)}."

    generic_matches = [
        t["term"] for t in terms if t["category"] == "generic_needs_coupling" and t["term"] in text_blob
    ]
    if generic_matches:
        coupling_rows = conn.execute("SELECT term FROM config_coupling_terms").fetchall()
        coupled_terms = [r["term"] for r in coupling_rows if r["term"] in text_blob]
        if coupled_terms:
            base_outcome = "PASS"
            base_reason = (
                f"Generic term(s) {generic_matches} coupled with sector/capability "
                f"term(s): {coupled_terms}."
            )
        else:
            base_outcome = "FLAG"
            base_reason = (
                f"Generic term(s) {generic_matches} present with no sector or capability "
                "coupling; not auto-passed on generic language alone."
            )

    # Compatibility path for older callers/tests that only exercise the text
    # heuristic. Real notice triage passes CPV evidence in, so this preserves
    # the current app path while keeping the legacy helper surface working.
    if cpv_primary is None and cpv_primary_inferred is False and not cpv_additional:
        return GateResult(base_outcome, base_reason)

    # CPV is evidence inside Gate 2 (v1.5), not a separate gate.
    scoped_prefixes = _sector_cpv_scope(conn, sector)
    if not cpv_primary:
        cpv_outcome, cpv_reason = "FLAG", "No CPV code present on this notice; unlisted, do not rate."
    elif scoped_prefixes is not None:
        allowed_display = ", ".join(f"{p}xxx" for p in scoped_prefixes)
        if any(cpv_primary.startswith(p) for p in scoped_prefixes):
            cpv_outcome = "PASS"
            cpv_reason = f"CPV {cpv_primary} is in {sector}'s allowed range ({allowed_display})."
        else:
            cpv_outcome = "FAIL"
            cpv_reason = f"CPV {cpv_primary} is outside {sector}'s allowed range ({allowed_display} only)."
        if cpv_primary_inferred:
            cpv_reason += " (primary CPV inferred)"
    else:
        cpv_outcome, cpv_reason = _lookup_cpv(conn, cpv_primary, text_blob)
        if cpv_primary_inferred:
            cpv_reason += " (primary CPV inferred)"

    # A sector-scoped CPV mismatch is a deterministic number comparison, not
    # a fuzzy keyword judgment call -- flagged so triage_notice can skip the
    # human double-check for this specific case, same as an unowned notice.
    cpv_scope_fail = scoped_prefixes is not None and cpv_outcome == "FAIL"

    if base_outcome == "FAIL" or cpv_outcome == "FAIL":
        return GateResult(
            "FAIL", f"{base_reason} CPV evidence: {cpv_reason}",
            extra={"cpv_scope_fail": cpv_scope_fail},
        )

    if base_outcome == "PASS" and cpv_outcome in ("PASS", "INFERRED_FIT"):
        return GateResult("PASS", f"{base_reason} CPV evidence: {cpv_reason}")

    # Anything uncertain in either source stays a FLAG and proceeds to Phase 2.
    return GateResult("FLAG", f"{base_reason} CPV evidence: {cpv_reason}")


def gate3_notice_stage(uk_stage: str) -> GateResult:
    if uk_stage in ("UK1", "UK2", "UK3", "UK4"):
        return GateResult("PASS", f"Live pre-award stage ({uk_stage}).")
    if uk_stage == "UK5":
        return GateResult("FAIL", "Award stage (UK5); route to closed/awarded handling.")
    return GateResult("FLAG", "UK stage is UNVERIFIED or not recognized; carry as open question to Phase 2.")


def gate5_framework(conn: sqlite3.Connection, text_blob: str, uk_stage: str) -> GateResult:
    keywords = conn.execute("SELECT term, category FROM config_framework_keywords").fetchall()

    call_off_matches = [k["term"] for k in keywords if k["category"] == "call_off" and k["term"] in text_blob]
    establishment_matches = [
        k["term"] for k in keywords if k["category"] == "establishment" and k["term"] in text_blob
    ]
    direct_matches = [k["term"] for k in keywords if k["category"] == "direct" and k["term"] in text_blob]

    if call_off_matches:
        frameworks = conn.execute("SELECT framework_name FROM config_trifork_frameworks").fetchall()
        on_framework = any(f["framework_name"].lower() in text_blob for f in frameworks)
        if on_framework:
            return GateResult(
                "PASS",
                f"Framework call-off detected ({', '.join(call_off_matches)}), Trifork is "
                "confirmed on the named framework.",
            )
        return GateResult(
            "FAIL",
            f"Framework call-off detected ({', '.join(call_off_matches)}); Trifork not "
            "yet on framework.",
        )

    if establishment_matches:
        return GateResult(
            "PASS", f"Framework establishment bid detected ({', '.join(establishment_matches)})."
        )

    if direct_matches:
        return GateResult("PASS", f"Direct open procurement detected ({', '.join(direct_matches)}).")

    if uk_stage in ("UK1", "UK2"):
        return GateResult(
            "MAYBE",
            "Route not yet decided: UK1/UK2 preliminary market engagement stage with no "
            "framework stated yet.",
        )

    return GateResult(
        "FLAG",
        "Framework status unclear; no framework or direct-procurement language detected, "
        "do not guess.",
    )


def gate3_framework(conn: sqlite3.Connection, text_blob: str, uk_stage: str) -> GateResult:
    """Backward-compatible alias for older tests and callers."""
    return gate5_framework(conn, text_blob, uk_stage)


def gate5_cpv(
    conn: sqlite3.Connection,
    cpv_primary: str | None,
    cpv_primary_inferred: bool,
    cpv_additional: list[str],
    text_blob: str,
) -> GateResult:
    """Backward-compatible CPV helper used by older tests and callers.

    The current app folds CPV evidence into Gate 2, but this helper still
    returns the CPV-only verdict so older callers keep working.
    """
    if not cpv_primary:
        return GateResult("FLAG", "No CPV code present on this notice; unlisted, do not rate.")

    primary_outcome, primary_reason = _lookup_cpv(conn, cpv_primary, text_blob)
    if cpv_primary_inferred:
        primary_reason += " (primary CPV inferred)"

    conflicting_additional: list[str] = []
    for code in cpv_additional:
        if code == cpv_primary:
            continue
        additional_outcome, _additional_reason = _lookup_cpv(conn, code, text_blob)
        if additional_outcome != primary_outcome:
            conflicting_additional.append(f"{code} ({additional_outcome})")

    if conflicting_additional:
        return GateResult(
            "FLAG",
            f"Primary CPV {cpv_primary}: {primary_reason}; conflicting additional CPV(s): "
            f"{', '.join(conflicting_additional)}.",
        )

    return GateResult(primary_outcome, primary_reason)


def gate4_window(
    tender_status: str | None,
    lot_statuses: list[str],
    tender_period_end: str | None,
    pme_due_date: str | None,
    future_notice_date: str | None,
) -> GateResult:
    now = datetime.now(timezone.utc)
    closed_statuses = {"complete", "cancelled", "withdrawn", "unsuccessful"}

    future_dt = _parse_date(future_notice_date)
    stage_still_ahead = bool(future_dt and future_dt.astimezone(timezone.utc) > now)

    is_closed = tender_status in closed_statuses or any(s in closed_statuses for s in lot_statuses)
    if is_closed:
        if stage_still_ahead:
            return GateResult(
                "MONITOR",
                f"Closed or awarded, but a further notice is expected ({future_notice_date}); "
                "tender stage still ahead.",
            )
        return GateResult("FAIL", f"Closed or awarded (status: {tender_status or 'UNVERIFIED'}).")

    deadline = tender_period_end or pme_due_date
    deadline_dt = _parse_date(deadline)
    if deadline_dt and deadline_dt.astimezone(timezone.utc) < now:
        if stage_still_ahead:
            return GateResult(
                "MONITOR",
                f"Deadline {deadline} has passed but tender stage still ahead per "
                f"{future_notice_date}.",
            )
        return GateResult(
            "FLAG",
            f"Deadline {deadline} has passed and no further stage is stated; status "
            "unclear, do not guess.",
        )

    return GateResult(
        "PASS", f"Open (status: {tender_status or 'UNVERIFIED'}, deadline: {deadline or 'none stated'})."
    )


def _lookup_cpv(conn: sqlite3.Connection, code: str, text_blob: str) -> tuple[str, str]:
    exact_rows = conn.execute(
        "SELECT list_type, condition_keyword, notes FROM config_cpv_lists WHERE cpv_code = ?",
        (code,),
    ).fetchall()
    for row in exact_rows:
        if row["condition_keyword"]:
            if row["condition_keyword"].lower() in text_blob:
                return row["list_type"], (row["notes"] or "exact CPV match, condition met")
            continue
        return row["list_type"], (row["notes"] or "exact CPV list match")

    prefix_row = conn.execute(
        "SELECT list_type, notes FROM config_cpv_lists WHERE cpv_code = ?", (code[:2],)
    ).fetchone()
    if prefix_row:
        return prefix_row["list_type"], (prefix_row["notes"] or "prefix bucket match")

    return "FLAG", "CPV code not in any documented list; unlisted, do not rate."


def filter3_scale(conn: sqlite3.Connection, indicative_value: str | None, text_blob: str) -> GateResult:
    config = conn.execute("SELECT * FROM config_scale_filter ORDER BY id DESC LIMIT 1").fetchone()
    if not config or not config["enabled"]:
        return GateResult("PASS", "Filter 3 is disabled.")

    amount = _extract_numeric_value(indicative_value)
    if amount is None or amount <= config["value_threshold"]:
        return GateResult(
            "PASS",
            f"Value not over Filter 3's £{config['value_threshold']:,.0f} threshold "
            f"(indicative value: {indicative_value or 'UNVERIFIED'}).",
        )

    si_primes = json.loads(config["si_prime_suppliers"])
    matched_primes = [p for p in si_primes if p.lower() in text_blob]
    if matched_primes:
        return GateResult(
            "FAIL",
            f"Over £{config['value_threshold']:,.0f} with a dominant global SI prime pool "
            f"mentioned ({', '.join(matched_primes)}). Filter 3, agreed {config['agreed_date']}.",
        )
    return GateResult(
        "PASS",
        f"Over £{config['value_threshold']:,.0f} but no global SI prime named; Filter 3 "
        "requires both conditions.",
    )


def run_gates(conn: sqlite3.Connection, notice_row: sqlite3.Row) -> dict[str, GateResult]:
    """Runs all five gates plus Filter 3, always, regardless of earlier
    outcomes (no short-circuit, per your decision)."""
    text_blob = notice_row["text_blob"] or ""
    cpv_additional = json.loads(notice_row["cpv_additional"]) if notice_row["cpv_additional"] else []
    lot_statuses = json.loads(notice_row["lot_statuses"]) if notice_row["lot_statuses"] else []

    results: dict[str, GateResult] = {}
    results["gate1"] = gate1_sector_owner(conn, notice_row["buyer"], text_blob)
    # Gate 2's CPV evidence can be sector-scoped (config_sector_cpv_scope) --
    # read the sector Gate 1 just found, not notice_row["sector"], which
    # isn't written back to the row until after run_gates returns.
    gate1_sector = results["gate1"].extra.get("sector")
    results["gate2"] = gate2_type_of_work(
        conn,
        text_blob,
        notice_row["cpv_primary"],
        bool(notice_row["cpv_primary_inferred"]),
        cpv_additional,
        sector=gate1_sector,
    )
    results["gate3"] = gate3_notice_stage(notice_row["uk_stage"])
    results["gate4"] = gate4_window(
        notice_row["tender_status"],
        lot_statuses,
        notice_row["tender_period_end"],
        notice_row["pme_due_date"],
        notice_row["future_notice_date"],
    )
    results["gate5"] = gate5_framework(conn, text_blob, notice_row["uk_stage"])
    results["filter3"] = filter3_scale(conn, notice_row["indicative_value"], text_blob)
    return results


def headline_outcome(results: dict[str, GateResult]) -> tuple[str, str, str]:
    """A FAIL anywhere is the headline, first FAIL in gate order if several --
    it's a stronger, more conclusive signal than a FLAG/MAYBE/MONITOR, so it
    must win even if an earlier gate in GATE_ORDER only flagged (2026-07-28
    fix: a Gate 4 closed/awarded FAIL was being masked by an earlier Gate 2/3
    FLAG, e.g. an UNVERIFIED stage, letting obviously-closed tenders reach
    Phase 2 instead of failing). Absent any FAIL, first non-PASS in gate
    order is the headline, same as before. All PASS means the notice passes
    Phase 1 clean."""
    for gate_key in GATE_ORDER:
        if results[gate_key].outcome == "FAIL":
            return gate_key, "FAIL", results[gate_key].reason
    for gate_key in GATE_ORDER:
        result = results[gate_key]
        if result.outcome != "PASS":
            return gate_key, result.outcome, result.reason
    return GATE_ORDER[0], "PASS", "All gates passed."


def _evaluate_and_record(
    conn: sqlite3.Connection, notice_id: int, notice_row: sqlite3.Row, actor: str, audit_action: str
) -> tuple[str, str, str, dict[str, GateResult]]:
    """Runs all gates, records a new triage_runs + gate_results set, and
    updates sector/owner from Gate 1 if it produced one. Shared by
    triage_notice (first pass) and retriage_notice (re-evaluation after a
    config correction). Does not touch notice status. Returns
    (headline_gate, headline_outcome, headline_reason, results) -- results is
    the full per-gate dict, so callers can inspect e.g. gate2's
    cpv_scope_fail marker without a second gates run."""
    results = run_gates(conn, notice_row)
    headline_gate, headline_out, headline_reason = headline_outcome(results)
    now = datetime.now(timezone.utc).isoformat()

    cursor = conn.execute(
        "INSERT INTO triage_runs (notice_id, headline_gate, headline_outcome, headline_reason, evaluated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (notice_id, headline_gate, headline_out, headline_reason, now),
    )
    triage_run_id = cursor.lastrowid

    for gate_key in GATE_ORDER:
        result = results[gate_key]
        conn.execute(
            "INSERT INTO gate_results "
            "(triage_run_id, notice_id, gate_number, gate_name, outcome, reason, evaluated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (triage_run_id, notice_id, gate_key, GATE_NAMES[gate_key], result.outcome, result.reason, now),
        )

    # Always set sector/owner to exactly what this evaluation found (never
    # COALESCE-preserve a stale value): on first triage sector/owner start
    # NULL so this is equivalent either way, but on a retriage after a
    # classification fix, a notice that no longer matches any sector must
    # actually clear back to NULL, not keep an outdated PASS.
    gate1_extra = results["gate1"].extra
    sector = gate1_extra.get("sector")
    owner = gate1_extra.get("owner")
    conn.execute(
        "UPDATE notices SET sector = ?, owner = ?, updated_at = ? WHERE id = ?",
        (sector, owner, now, notice_id),
    )

    conn.commit()
    log_audit(
        conn,
        "notice",
        str(notice_id),
        audit_action,
        actor,
        headline_reason,
        {"headline_gate": headline_gate, "headline_outcome": headline_out},
    )
    return headline_gate, headline_out, headline_reason, results


def triage_notice(conn: sqlite3.Connection, notice_id: int, actor: str = "system_triage") -> str:
    """Runs Phase 1 triage on one notice, records every gate result, moves
    the notice from NEW to PHASE1_TRIAGED, then routes based on headline outcome:
    - PASS: skip owner review, go straight to PHASE2_SCOPED for the AI scope read
    - FLAG or MAYBE: also go to PHASE2_SCOPED, to gather more data before an
      escalation decision, rather than auto-escalating on the Phase 1 result alone
    - FAIL: go to TO_REVIEW for owner double-check -- UNLESS the FAIL needs no
      human judgment call: no sector/owner assigned at all (nobody to review
      it anyway), a Gate 3 UK5/award-stage FAIL (unambiguous), or a Gate 2
      sector-scoped CPV mismatch (a plain number comparison). Any of those
      auto-rejects instead (2026-07-28 decisions). A fuzzy FAIL with an owner
      still assigned (a Gate 2 text-based fail term, or the non-scoped global
      CPV list) still gets a real double-check -- those calls can be wrong.
    - MONITOR: go to MONITORING status
    Returns the headline outcome."""
    notice_row = conn.execute("SELECT * FROM notices WHERE id = ?", (notice_id,)).fetchone()
    if notice_row is None:
        raise ValueError(f"No notice with id {notice_id}")

    headline_gate, headline_out, headline_reason, gate_results = _evaluate_and_record(
        conn, notice_id, notice_row, actor, "triage_run"
    )
    now = datetime.now(timezone.utc).isoformat()

    current_status = Status(notice_row["status"])
    if current_status == Status.NEW:
        validate_transition(current_status, Status.PHASE1_TRIAGED)
        conn.execute(
            "UPDATE notices SET status = ?, updated_at = ? WHERE id = ?",
            (Status.PHASE1_TRIAGED.value, now, notice_id),
        )
        conn.commit()
        log_status_change(conn, notice_id, current_status.value, Status.PHASE1_TRIAGED.value, actor, "Phase 1 triage complete")
        current_status = Status.PHASE1_TRIAGED

    # Route based on headline outcome per SPEC B1 + user policy:
    # - PASS: Phase 2 scope read
    # - FLAG/MAYBE: Phase 2 scope read (gather more data before escalating)
    # - FAIL: Owner double-check review (TO_REVIEW)
    # - MONITOR: Monitoring status (MONITORING)
    if headline_out == "PASS":
        next_status = Status.PHASE2_SCOPED
        reason = "Phase 1 passed all gates, proceeding to Phase 2 scope read"
    elif headline_out in ("FLAG", "MAYBE"):
        next_status = Status.PHASE2_SCOPED
        reason = f"Phase 1 {headline_out} - proceeding to Phase 2 scope read for deeper assessment before escalation decision"
    elif headline_out == "FAIL":
        next_status = Status.TO_REVIEW
        reason = headline_reason  # Owner reviews the FAIL as double-check
    elif headline_out == "MONITOR":
        next_status = Status.MONITORING
        reason = headline_reason
    else:
        next_status = Status.TO_REVIEW
        reason = headline_reason

    validate_transition(current_status, next_status)
    conn.execute(
        "UPDATE notices SET status = ?, updated_at = ? WHERE id = ?",
        (next_status.value, now, notice_id),
    )
    conn.commit()
    log_status_change(conn, notice_id, current_status.value, next_status.value, actor, reason)

    # Auto-close a TO_REVIEW FAIL instead of waiting on a human, but only for
    # cases with no real judgment call involved (2026-07-28 decisions):
    # - no sector/owner assigned: no queue filters by owner=NULL, so it would
    #   sit there invisibly forever otherwise.
    # - Gate 3 FAIL: only ever UK5 (award/closed) -- unambiguous, done.
    # - Gate 4 FAIL: only ever an already closed/awarded tender (complete,
    #   cancelled, withdrawn, unsuccessful, with no further stage expected)
    #   -- also unambiguous, nothing left to bid on.
    # - Gate 2 FAIL specifically from a sector-scoped CPV mismatch: a plain
    #   number-prefix comparison, not a keyword heuristic that could be wrong.
    # A fuzzy FAIL with an owner already assigned (e.g. a Gate 2 text-based
    # fail term, or the global non-scoped CPV list) still gets a real
    # owner's double-check as before -- those calls can be wrong.
    # Checked across ALL gates, not just whichever one won the headline --
    # a notice can independently FAIL two gates at once (e.g. a text-based
    # Gate 2 fail term AND an already-closed Gate 4), and headline_outcome
    # only surfaces the first one in gate order. If ANY gate is a
    # deterministic FAIL, auto-reject regardless of which gate is headlined.
    refreshed = conn.execute("SELECT owner FROM notices WHERE id = ?", (notice_id,)).fetchone()
    is_deterministic_fail = (
        gate_results["gate3"].outcome == "FAIL"
        or gate_results["gate4"].outcome == "FAIL"  # only ever an already closed/awarded tender
        or (gate_results["gate2"].outcome == "FAIL" and gate_results["gate2"].extra.get("cpv_scope_fail"))
    )
    if next_status == Status.TO_REVIEW and (refreshed["owner"] is None or is_deterministic_fail):
        validate_transition(Status.TO_REVIEW, Status.REJECTED)
        now2 = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE notices SET status = ?, auto_rejected_unowned = 1, updated_at = ? WHERE id = ?",
            (Status.REJECTED.value, now2, notice_id),
        )
        conn.commit()
        log_status_change(
            conn, notice_id, Status.TO_REVIEW.value, Status.REJECTED.value, actor,
            "Auto-rejected: no human judgment call needed here. " + headline_reason,
        )

    # No auto-escalation at Phase 1 - FLAGs get Phase 2 assessment first

    return headline_out


def retriage_notice(conn: sqlite3.Connection, notice_id: int, actor: str = "system_retriage") -> str:
    """Re-evaluates all gates for a notice after a config correction (e.g. a
    sector keyword fix), without moving its status. Deliberately does not
    touch status at all: routing a re-triaged notice onward (to MONITOR or
    ESCALATED_TO_VICTORIA, generating a fresh brief if warranted) is workflow
    orchestration, not gate logic, so it lives in
    workflow.approvals.retriage_and_route, not here.

    Only sane to call on a notice still in AWAITING_PHASE1_APPROVAL that no
    human has acted on yet; callers are responsible for that check (see
    workflow.approvals.retriage_and_route, which enforces it). Returns the
    new headline outcome."""
    notice_row = conn.execute("SELECT * FROM notices WHERE id = ?", (notice_id,)).fetchone()
    if notice_row is None:
        raise ValueError(f"No notice with id {notice_id}")

    _, headline_out, _, _ = _evaluate_and_record(conn, notice_id, notice_row, actor, "retriage_run")
    return headline_out

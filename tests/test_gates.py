from savvy_scout.sweep.dedupe import upsert_notice
from savvy_scout.sources.ocds_parser import parse_release_package
from savvy_scout.triage.gates import (
    filter3_scale,
    gate1_sector_owner,
    gate2_type_of_work,
    gate3_framework,
    gate4_window,
    gate5_cpv,
    triage_notice,
    _lookup_cpv,
)


# --- Gate 1: buyer sector and owner ---------------------------------------


def test_gate1_airport_is_fail(conn):
    result = gate1_sector_owner(conn, "Gatwick Airport Limited", "airport terminal systems")
    assert result.outcome == "FAIL"


def test_gate1_energy_owner_is_mark(conn):
    result = gate1_sector_owner(conn, "National Grid", "smart grid monitoring for energy distribution")
    assert result.outcome == "PASS"
    assert result.extra["sector"] == "Energy"
    assert result.extra["owner"] == "Mark"


def test_gate1_contested_sector_flags(conn):
    # Bare "bank" and "energy" alone no longer match (generic, needs coupling)
    # -- genuinely coupled to both here: "payments platform" for Fintech,
    # "smart grid" for Energy, so both count and it's a true contested match.
    result = gate1_sector_owner(
        conn,
        "Some Bank",
        "real-time payments platform integration with smart grid billing systems for our energy trading desk",
    )
    assert result.outcome == "FLAG"


def test_gate1_bare_generic_keyword_alone_fails(conn):
    # "bank" with no product/capability coupling term nearby is not enough
    # evidence of a Fintech notice -- this is what used to wrongly classify
    # things like "EPA's for 29 Apprentices" as Fintech. Per the 2026-07-21
    # update, an industry mention with no coupling signal is out of sector:
    # it FAILs with no owner assigned, and does not need a human
    # double-check, same as a notice with no sector mention at all.
    result = gate1_sector_owner(conn, "Some Bank", "grounds maintenance and repairs contract")
    assert result.outcome == "FAIL"
    assert "Fintech" in result.reason


def test_gate1_no_sector_mention_at_all_fails(conn):
    result = gate1_sector_owner(conn, "Acme Widgets Ltd", "supply of steel fittings to spec B12")
    assert result.outcome == "FAIL"


def test_gate1_generic_keyword_with_capability_coupling_matches(conn):
    # "energy" (generic) + "distributed systems" (capability coupling, sector-
    # agnostic) is enough evidence, without needing an Energy-specific term.
    result = gate1_sector_owner(
        conn, "Some Utility Co", "distributed systems platform for energy network monitoring"
    )
    assert result.outcome == "PASS"
    assert result.extra["sector"] == "Energy"


def test_gate1_identity_keyword_matches_without_coupling(conn):
    # A specific buyer name still matches unconditionally, no coupling needed.
    result = gate1_sector_owner(conn, "EasyJet Airline Group", "catering supplies for cabin crew")
    assert result.outcome == "PASS"
    assert result.extra["sector"] == "Aviation"


def test_gate1_no_sector_match_fails(conn):
    result = gate1_sector_owner(conn, "Unrelated Buyer", "totally unrelated procurement text")
    assert result.outcome == "FAIL"


def test_gate1_nhs_v2_digital_health_keyword_matches(conn):
    # Trifork scouting skill v2, Section 3a (2026-08-11): digital-health
    # vocabulary specific enough to identify NHS notices on its own.
    result = gate1_sector_owner(conn, "Some NHS Trust", "procurement of a new digital pathology service")
    assert result.outcome == "PASS"
    assert result.extra["sector"] == "NHS and Healthcare"


def test_gate1_nhs_v2_exclusion_terms_stop_sector_match(conn):
    # "health" alone is generic_needs_coupling, and "catering" is a Section
    # 3a exclusion -- a catering notice for an NHS trust must not match.
    result = gate1_sector_owner(conn, "Some NHS Trust", "provision of catering services to staff canteens")
    assert result.outcome == "FAIL"


# --- CPV: 48xxxxxx Corax/Tiris Messenger conditional PASS -------------------


def test_cpv_48_with_corax_passes(conn):
    # haystack is assumed already lowercased (see contains_keyword's
    # docstring) -- text_blob is lowercased at ingestion in the real
    # pipeline (ocds_parser.py), so tests must match that contract too.
    outcome, reason = _lookup_cpv(conn, "48000000", "delivery of the corax ai analytics platform")
    assert outcome == "PASS"
    assert "Corax" in reason


def test_cpv_48_with_tiris_passes(conn):
    outcome, reason = _lookup_cpv(conn, "48000000", "provision of tiris messenger for safety-critical comms")
    assert outcome == "PASS"
    assert "Tiris" in reason


def test_cpv_48_with_no_named_product_is_flag_not_blanket_pass(conn):
    # Confirmed ruling: 48xxxxxx is never a blanket pass, even with no
    # named Trifork product match.
    outcome, reason = _lookup_cpv(conn, "48000000", "procurement of a generic case management system")
    assert outcome == "FLAG"


def test_gate2_cpv48_sector_scoped_still_requires_named_product(conn):
    # Regression: every sector's config_sector_cpv_scope allows the "48"
    # prefix, so without the special-case this blanket-passed any
    # 48xxxxxx notice regardless of Corax/Tiris -- confirmed this stays a
    # FLAG for NHS, not an automatic PASS, when no named product is present.
    result = gate2_type_of_work(
        conn,
        "provision of a generic case management system",
        cpv_primary="48000000",
        sector="NHS and Healthcare",
    )
    assert result.outcome == "FLAG"


def test_gate2_sector_cpv_scope_mismatch_no_longer_fails(conn):
    # 2026-08-15, Mark's correction: a sector-CPV-scope mismatch alone is
    # corroboration only, never a fail condition. A genuinely non-digital
    # CPV outside Energy's 72/48 range, with no text signal either, should
    # FLAG (not FAIL) for a human type-of-work call.
    result = gate2_type_of_work(
        conn, "unrelated procurement text", cpv_primary="79713000", sector="Energy",
    )
    assert result.outcome == "FLAG"


def test_gate2_disqualifier_cpv_still_fails_regardless_of_sector_scope(conn):
    # A genuine DISQUALIFIER CPV (33xxx medical goods) is still the only
    # CPV-based fail condition, even though it also falls outside Energy's
    # configured 72/48 range.
    result = gate2_type_of_work(
        conn, "unrelated procurement text", cpv_primary="33140000", sector="Energy",
    )
    assert result.outcome == "FAIL"


def test_gate2_cpv48_sector_scoped_passes_with_corax(conn):
    result = gate2_type_of_work(
        conn,
        "bespoke build of the corax ai analytics platform for clinical data",
        cpv_primary="48000000",
        sector="NHS and Healthcare",
    )
    assert result.outcome == "PASS"


# --- Gate 2: type of work ---------------------------------------------------


def test_gate2_fail_term(conn):
    result = gate2_type_of_work(conn, "seeking a managed service provider")
    assert result.outcome == "FAIL"


def test_gate2_unconditional_pass_term(conn):
    result = gate2_type_of_work(conn, "requires a bespoke build of a new system")
    assert result.outcome == "PASS"


def test_gate2_generic_term_alone_now_passes(conn):
    # 2026-08-15, Mark's correction: a generic term no longer needs pairing
    # with a coupling term -- any digital/software/data/platform signal at
    # all is sufficient for PASS (previously FLAGged as "uncoupled").
    result = gate2_type_of_work(conn, "seeking a new platform for our business")
    assert result.outcome == "PASS"


def test_gate2_generic_term_coupled_with_sector_passes(conn):
    result = gate2_type_of_work(conn, "seeking a new data platform for our rail operations")
    assert result.outcome == "PASS"


def test_gate2_generic_term_coupled_with_capability_passes(conn):
    result = gate2_type_of_work(conn, "a digital identity capability built on erlang")
    assert result.outcome == "PASS"


def test_gate2_no_keyword_flags(conn):
    result = gate2_type_of_work(conn, "unrelated text with no gate 2 keywords at all")
    assert result.outcome == "FLAG"


# --- Gate 3: framework status ------------------------------------------------


def test_gate3_call_off_not_on_framework_fails(conn):
    result = gate3_framework(conn, "this is a framework call-off for services", "UK3")
    assert result.outcome == "FAIL"


def test_gate3_establishment_passes(conn):
    result = gate3_framework(conn, "we are running a framework establishment exercise", "UK3")
    assert result.outcome == "PASS"


def test_gate3_direct_procurement_passes(conn):
    result = gate3_framework(conn, "this is an open tender for direct award", "UK3")
    assert result.outcome == "PASS"


def test_gate3_pme_no_framework_now_passes(conn):
    # 2026-08-15, Mark's correction: no framework language at all defaults
    # to PASS (previously MAYBE at UK1/UK2) -- silence on procurement
    # mechanics is normal, not evidence of a blocking framework.
    result = gate3_framework(conn, "we are seeking market input on our future route", "UK2")
    assert result.outcome == "PASS"


def test_gate3_unclear_non_pme_now_passes(conn):
    # 2026-08-15, Mark's correction: same default-to-PASS applies outside
    # UK1/UK2 too (previously FLAGged as "unclear").
    result = gate3_framework(conn, "we are seeking market input on our future route", "UK3")
    assert result.outcome == "PASS"


# --- Gate 4: window (fixed dates, not real "now", to keep this deterministic) --


def test_gate4_closed_no_future_notice_fails():
    result = gate4_window("complete", [], "2000-01-01T00:00:00+00:00", None, None)
    assert result.outcome == "FAIL"


def test_gate4_closed_with_future_notice_monitors():
    result = gate4_window("complete", [], "2000-01-01T00:00:00+00:00", None, "2999-01-01T00:00:00+00:00")
    assert result.outcome == "MONITOR"


def test_gate4_open_future_deadline_passes():
    result = gate4_window("planning", ["planning"], None, "2999-01-01T00:00:00+00:00", None)
    assert result.outcome == "PASS"


def test_gate4_deadline_passed_no_further_stage_flags():
    result = gate4_window("planning", ["planning"], None, "2000-01-01T00:00:00+00:00", None)
    assert result.outcome == "FLAG"


def test_gate4_deadline_passed_with_future_stage_monitors():
    result = gate4_window(
        "planning", ["planning"], None, "2000-01-01T00:00:00+00:00", "2999-01-01T00:00:00+00:00"
    )
    assert result.outcome == "MONITOR"


# --- Gate 5: CPV codes -------------------------------------------------------


def test_gate5_pass_list_code(conn):
    result = gate5_cpv(conn, "72200000", False, [], "some notice text")
    assert result.outcome == "PASS"


def test_gate5_conditional_fail_met(conn):
    result = gate5_cpv(conn, "80420000", False, [], "requires security testing services")
    assert result.outcome == "FAIL"


def test_gate5_conditional_fail_not_met_falls_to_flag(conn):
    result = gate5_cpv(conn, "80420000", False, [], "unrelated requirement, no testing mentioned")
    assert result.outcome == "FLAG"


def test_gate5_unlisted_code_flags(conn):
    result = gate5_cpv(conn, "99999999", False, [], "some notice text")
    assert result.outcome == "FLAG"


def test_gate5_sample_notice_multi_cpv_conflict(conn, sample_ocds_package):
    parsed = parse_release_package(sample_ocds_package, source="Find a Tender")[0]
    result = gate5_cpv(
        conn,
        parsed.notice.cpv_primary,
        parsed.notice.cpv_primary_inferred,
        parsed.notice.cpv_additional,
        parsed.text_blob,
    )
    # Primary 48800000 -> 48xxx bucket -> FLAG. Additional 50300000 (FAIL) and
    # 72100000 (INFERRED_FIT) both conflict with the primary outcome.
    assert result.outcome == "FLAG"
    assert "50300000" in result.reason
    assert "72100000" in result.reason
    assert "inferred" in result.reason.lower()


# --- Filter 3: scale and incumbents ------------------------------------------


def test_filter3_disabled_always_passes(conn):
    conn.execute("UPDATE config_scale_filter SET enabled = 0")
    result = filter3_scale(conn, "600000000 GBP", "led by accenture as prime")
    assert result.outcome == "PASS"


def test_filter3_over_threshold_with_si_prime_fails(conn):
    result = filter3_scale(conn, "600000000 GBP", "led by accenture as prime contractor")
    assert result.outcome == "FAIL"


def test_filter3_over_threshold_no_si_prime_passes(conn):
    result = filter3_scale(conn, "600000000 GBP", "led by a small specialist supplier")
    assert result.outcome == "PASS"


def test_filter3_under_threshold_passes(conn):
    result = filter3_scale(conn, "1000000 GBP", "led by accenture as prime contractor")
    assert result.outcome == "PASS"


def test_filter3_no_value_passes(conn):
    result = filter3_scale(conn, None, "led by accenture as prime contractor")
    assert result.outcome == "PASS"


# --- Full pipeline smoke test on the real sample notice ----------------------


def test_triage_sample_notice_end_to_end(conn, sample_ocds_package):
    parsed = parse_release_package(sample_ocds_package, source="Find a Tender")[0]
    notice_id = upsert_notice(conn, parsed)

    headline = triage_notice(conn, notice_id)

    # Gate 1 passes (Rail and Transport, owner Mark) but Gate 2 fails on
    # "managed service", which comes before Gates 3-5 in gate order, so it's
    # the headline regardless of the real clock at test time (Gate 4 is
    # date-dependent and deliberately not asserted here).
    assert headline == "FAIL"

    row = conn.execute("SELECT * FROM notices WHERE id = ?", (notice_id,)).fetchone()
    assert row["sector"] == "Rail and Transport"
    assert row["owner"] == "Mark"
    assert row["status"] in ("TO_REVIEW", "MONITOR")

    gate_rows = conn.execute(
        "SELECT gate_number, outcome FROM gate_results WHERE notice_id = ?", (notice_id,)
    ).fetchall()
    assert len(gate_rows) == 6
    outcomes = {r["gate_number"]: r["outcome"] for r in gate_rows}
    assert outcomes["gate1"] == "PASS"
    assert outcomes["gate2"] == "FAIL"

from savvy_scout.triage.sector_classifier import (
    classify_sector,
    contains_keyword,
    is_contested,
    uncoupled_candidate_sectors,
)


def test_contains_keyword_respects_word_boundaries():
    """2026-08-10 finding, confirmed live: "lner" (Rail and Transport's
    identity keyword for the LNER train operator) was matching inside
    "vulnerable" via plain substring search -- nothing to do with trains.
    Same class of bug already worked around once for "ai" inside
    "maintenance"; this is the general fix."""
    assert contains_keyword("a replacement service for vulnerable residents", "lner") is False
    assert contains_keyword("lner trains were delayed", "lner") is True
    assert contains_keyword("services operated by lner-owned depots", "lner") is True


def test_council_with_vulnerable_residents_text_no_longer_falsely_contests_rail(conn):
    """Direct regression for the real notice that surfaced this: North
    Hertfordshire District Council's alarm-receiving-centre notice, which
    mentions "vulnerable residents," was wrongly flagged as contested with
    Rail and Transport purely because "lner" is a substring of
    "vulnerable"."""
    buyer = "North Hertfordshire District Council"
    text_blob = "replacement alarm receiving centre platform supporting vulnerable residents"

    assert classify_sector(conn, buyer, text_blob) == "Central and Local Government"
    assert is_contested(conn, buyer, text_blob) is False


def test_health_and_hospital_now_require_coupling_not_unconditional_identity(conn):
    """2026-08-10, explicit request: "health"/"hospital" are far too
    generic to be unconditional identity matches for NHS and Healthcare --
    ordinary council tenders mention "health and wellbeing" outcomes
    constantly with nothing to do with the NHS. A bare mention with no
    coupling evidence must not match at all; it should surface as an
    uncoupled candidate instead, same as Energy's "energy" or Fintech's
    "payments" already do."""
    buyer = "Some Regional Authority"
    text_blob = "young persons accommodation and support services with a focus on health outcomes"

    assert classify_sector(conn, buyer, text_blob) is None
    assert "NHS and Healthcare" in uncoupled_candidate_sectors(conn, buyer, text_blob)

    # Still matches when a real coupling term (a capability/product signal) is present.
    coupled_text = "a hospital patient records software platform"
    assert classify_sector(conn, "Some Buyer", coupled_text) == "NHS and Healthcare"


def test_identity_match_wins_over_a_different_sectors_generic_coupled_match(conn):
    """2026-08-10 finding, confirmed live against 9/9 sampled real council
    notices: a buyer with a clean identity match ("X Council") was getting
    contested and left unassigned because the notice text ALSO happened to
    mention "payments" (Fintech's generic keyword) alongside a coupling
    term like "platform" -- ordinary council business (council tax
    payments), not evidence the buyer is actually in Fintech. An identity
    match must be authoritative over a different sector's generic+coupling
    match."""
    buyer = "Bristol City Council"
    text_blob = "provision of a council tax payments platform for online payments processing"

    assert classify_sector(conn, buyer, text_blob) == "Central and Local Government"
    assert is_contested(conn, buyer, text_blob) is False


def test_two_identity_matches_still_genuinely_contest_each_other(conn):
    """The fix only suppresses a generic+coupling match against an existing
    identity match -- two REAL identity matches (buyer/notice text
    genuinely naming two different sectors' specific entities) must still
    contest, since that's real ambiguity, not incidental text noise."""
    buyer = "Some Council"
    text_blob = "in partnership with Barclays for a joint banking and local services initiative"

    assert classify_sector(conn, buyer, text_blob) is None
    assert is_contested(conn, buyer, text_blob) is True


def test_generic_coupled_match_still_works_with_no_identity_present(conn):
    """Unaffected by the fix: a buyer with no identity match of its own,
    matching one sector's generic keyword alongside a coupling term, still
    classifies cleanly."""
    buyer = "Some Regional Authority"
    text_blob = "supply of a smart grid energy management software platform"

    assert classify_sector(conn, buyer, text_blob) == "Energy"
    assert is_contested(conn, buyer, text_blob) is False


def test_uncoupled_generic_keyword_with_no_identity_still_flagged_as_candidate(conn):
    """Also unaffected: a bare industry-word mention with no coupling
    evidence and no identity match anywhere still surfaces as an uncoupled
    candidate (Gate 1 FLAGs it, rather than silently failing or matching)."""
    buyer = "Some Regional Authority"
    text_blob = "provision of grounds maintenance services near an energy substation"

    assert classify_sector(conn, buyer, text_blob) is None
    assert is_contested(conn, buyer, text_blob) is False
    assert "Energy" in uncoupled_candidate_sectors(conn, buyer, text_blob)


def test_natural_england_type_buyer_has_no_keyword_match_at_all(conn):
    """Confirmed live 2026-08-10: arm's-length bodies/agencies without
    council/government/ministry-style wording in their name aren't
    covered by any current sector or Central/Local Government keyword --
    a real, separate coverage gap from the contested-matching fix above."""
    buyer = "Natural England"
    text_blob = "culling of deer as part of a nature reserve management programme"

    assert classify_sector(conn, buyer, text_blob) is None
    assert is_contested(conn, buyer, text_blob) is False
    assert uncoupled_candidate_sectors(conn, buyer, text_blob) == set()

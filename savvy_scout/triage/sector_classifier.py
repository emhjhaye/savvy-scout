"""Buyer/notice -> sector classification, keyword-based (config_sector_keywords).
Heuristic pending a confirmed buyer list per sector (SPEC.md open question 2).
Shared by Gate 1 and the expiry radar so both agree on what counts as
"in scope sectors".

Two keyword categories, the same "generic needs coupling" pattern Gate 2
already uses (triage.gates.gate2_type_of_work):
- identity: a buyer/company name or specific-enough term (easyjet, national
  grid, ofgem) -- matches the sector on its own.
- generic_needs_coupling: bare industry vocabulary (energy, electricity,
  bank, payments, rail, airline...) that also matches unrelated non-IT work
  from the same buyer/industry (steel fittings, apprenticeship payments,
  academy-trust electricity contracts, grounds maintenance). Only counts as
  a confident sector match alongside a real capability or product-coupling
  term from config_coupling_terms. A generic keyword with no coupling
  evidence is not "no signal" (SPEC.md: never fail if unsure) -- it's an
  uncoupled candidate, surfaced separately so Gate 1 can FLAG it rather than
  FAIL it outright."""

import sqlite3

# A few config_coupling_terms rows are themselves the same bare industry word
# as a generic_needs_coupling keyword (e.g. "energy" is listed as Energy's own
# sector coupling term, for Gate 2's looser purposes). Counting those here
# would make the coupling check circular -- the bare word "proving" its own
# match -- so they're excluded for sector classification specifically. Gate
# 2's own use of config_coupling_terms is unaffected.
_CIRCULAR_COUPLING_TERMS = {"energy", "airline", "rail", "transport", "fintech"}


def _haystack(buyer: str | None, text_blob: str) -> str:
    return f"{(buyer or '').lower()}\n{text_blob.lower()}"


def _has_coupling(conn: sqlite3.Connection, sector: str, haystack: str) -> bool:
    rows = conn.execute(
        "SELECT term FROM config_coupling_terms WHERE kind = 'capability' OR sector = ?",
        (sector,),
    ).fetchall()
    return any(
        row["term"].lower() not in _CIRCULAR_COUPLING_TERMS and row["term"].lower() in haystack
        for row in rows
    )


def _has_exclusion(conn: sqlite3.Connection, sector: str, haystack: str) -> bool:
    rows = conn.execute(
        "SELECT term FROM config_exclusion_terms WHERE sector = ?", (sector,)
    ).fetchall()
    return any(row["term"].lower() in haystack for row in rows)


class _Classification:
    __slots__ = ("matched", "uncoupled")

    def __init__(self, matched: set[str], uncoupled: set[str]):
        self.matched = matched
        self.uncoupled = uncoupled


def _classify(conn: sqlite3.Connection, buyer: str | None, text_blob: str) -> _Classification:
    haystack = _haystack(buyer, text_blob)
    rows = conn.execute("SELECT sector, keyword, category FROM config_sector_keywords").fetchall()

    identity_sectors: set[str] = set()
    generic_sectors: set[str] = set()
    for row in rows:
        if row["keyword"].lower() not in haystack:
            continue
        if row["category"] == "generic_needs_coupling":
            generic_sectors.add(row["sector"])
        else:
            identity_sectors.add(row["sector"])

    matched = set(identity_sectors)
    uncoupled: set[str] = set()
    for sector in generic_sectors - identity_sectors:
        if _has_coupling(conn, sector, haystack):
            matched.add(sector)
        else:
            uncoupled.add(sector)

    # An exclusion term overrides any path to matching that sector (identity
    # or coupling), and also rules it out as an "uncoupled candidate" -- an
    # excluded sector isn't ambiguous, it's a confident non-match.
    matched = {s for s in matched if not _has_exclusion(conn, s, haystack)}
    uncoupled = {s for s in uncoupled if not _has_exclusion(conn, s, haystack)}

    return _Classification(matched=matched, uncoupled=uncoupled)


def classify_sector(conn: sqlite3.Connection, buyer: str | None, text_blob: str) -> str | None:
    """Returns the matched sector name, or None if no keyword matched, or
    only a generic keyword matched with no coupling evidence (ambiguous, see
    uncoupled_candidate_sectors), or more than one sector matched (contested,
    see is_contested)."""
    matched = _classify(conn, buyer, text_blob).matched
    if len(matched) == 1:
        return next(iter(matched))
    return None


def is_contested(conn: sqlite3.Connection, buyer: str | None, text_blob: str) -> bool:
    """True when more than one sector counts as a confident match (as
    opposed to zero)."""
    return len(_classify(conn, buyer, text_blob).matched) > 1


def uncoupled_candidate_sectors(conn: sqlite3.Connection, buyer: str | None, text_blob: str) -> set[str]:
    """Sectors with a bare industry-word mention but no coupling evidence and
    no identity match either. Used by Gate 1 to FLAG ("mentions the
    industry, unclear if it's IT work") instead of FAILing a notice that
    classify_sector couldn't confidently place."""
    classification = _classify(conn, buyer, text_blob)
    # If something else already matched confidently, this isn't the ambiguous
    # no-sector case Gate 1 needs -- classify_sector/is_contested already
    # cover it.
    if classification.matched:
        return set()
    return classification.uncoupled

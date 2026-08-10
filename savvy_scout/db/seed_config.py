"""Seeds config tables from SPEC.md's literal values, with your decisions on
the flagged disagreements applied (Energy owner, Gate 2 coupling rule, scale
filter toggle, CPV list provenance). Every table only seeds when empty, so a
config change made via the admin tab (Phase B) or by hand is never overwritten
by a later run."""

import json
import sqlite3
from datetime import datetime, timezone

from savvy_scout.logging_util import log_audit

SEEDED_BY = "system_seed"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _table_empty(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"] == 0


def seed_owner_map(conn: sqlite3.Connection) -> None:
    if not _table_empty(conn, "config_owner_map"):
        return
    now = _now()
    rows = [
        ("NHS and Healthcare", "Hammad", None),
        ("Central and Local Government", "Kanvesh", None),
        ("Fintech", "Mark", None),
        ("Aviation", "Mark", "Airlines only. Airports, ATC and defence aviation fail Gate 1."),
        ("Rail and Transport", "Mark", None),
        (
            "Energy",
            "Mark",
            "Moved from Kanvesh to Mark per Victoria's verbal sector confirmation "
            "in the references, overriding SPEC.md's original draft. Formal "
            "confirmation and removal from Kanvesh's scope is an open question "
            "for Victoria, see README.",
        ),
    ]
    conn.executemany(
        "INSERT INTO config_owner_map (sector, owner, notes, updated_at, updated_by) "
        "VALUES (?, ?, ?, ?, ?)",
        [(sector, owner, notes, now, SEEDED_BY) for sector, owner, notes in rows],
    )
    conn.commit()
    log_audit(conn, "config", "config_owner_map", "settings_change", SEEDED_BY, "initial seed")


GENERIC = "generic_needs_coupling"
IDENTITY = "identity"

SECTOR_KEYWORDS = [
        # NHS/Central Gov keywords are all bare industry vocabulary too (health,
        # council, government), but that sector's activation is an open question
        # for Kanvesh (see README), not a code decision -- left as unconditional
        # 'identity' matches, unchanged, until that's resolved.
        ("NHS and Healthcare", "nhs", IDENTITY),
        ("NHS and Healthcare", "health", IDENTITY),
        ("NHS and Healthcare", "hospital", IDENTITY),
        ("NHS and Healthcare", "clinical commissioning", IDENTITY),
        ("NHS and Healthcare", "integrated care board", IDENTITY),
        ("NHS and Healthcare", "foundation trust", IDENTITY),
        ("Central and Local Government", "council", IDENTITY),
        ("Central and Local Government", "department for", IDENTITY),
        ("Central and Local Government", "cabinet office", IDENTITY),
        ("Central and Local Government", "home office", IDENTITY),
        ("Central and Local Government", "ministry of", IDENTITY),
        ("Central and Local Government", "borough", IDENTITY),
        ("Central and Local Government", "county council", IDENTITY),
        ("Central and Local Government", "city council", IDENTITY),
        ("Central and Local Government", "government", IDENTITY),
        # Bare industry vocabulary: matches non-IT work too (an EPA payments
        # notice, a "food bank" mention) so it needs a product/capability
        # coupling term from config_coupling_terms to count. 2026-07-20, after
        # a live sweep showed these matching e.g. "PfH - Responsive Repairs"
        # and "EPA's for 29 Apprentices" as Fintech.
        ("Fintech", "bank", GENERIC),
        ("Fintech", "payments", GENERIC),
        ("Fintech", "clearing", GENERIC),
        ("Fintech", "financial conduct", IDENTITY),
        ("Fintech", "fintech", IDENTITY),
        ("Fintech", "building society", IDENTITY),
        ("Fintech", "vocalink", IDENTITY),
        # Named buyers/companies below are an unconfirmed heuristic (open
        # question 2), added 2026-07-19 after a live sweep showed the generic
        # terms above missing real named-company notices entirely.
        ("Fintech", "barclays", IDENTITY),
        ("Fintech", "hsbc", IDENTITY),
        ("Fintech", "lloyds", IDENTITY),
        ("Fintech", "natwest", IDENTITY),
        ("Fintech", "santander", IDENTITY),
        ("Fintech", "monzo", IDENTITY),
        ("Fintech", "revolut", IDENTITY),
        ("Fintech", "nationwide", IDENTITY),
        ("Fintech", "starling bank", IDENTITY),
        ("Fintech", "metro bank", IDENTITY),
        ("Fintech", "worldpay", IDENTITY),
        ("Fintech", "mastercard", IDENTITY),
        ("Fintech", "visa europe", IDENTITY),  # not bare "visa": collides with travel/immigration visas
        ("Fintech", "virgin money", IDENTITY),
        ("Fintech", "standard chartered", IDENTITY),
        ("Fintech", "danske bank", IDENTITY),
        # Bare "airline(s)"/"airways" also matches non-IT work for an airline
        # buyer (catering, ground handling, hardware); needs coupling.
        ("Aviation", "airline", GENERIC),
        ("Aviation", "airways", GENERIC),
        ("Aviation", "airlines", GENERIC),
        ("Aviation", "easyjet", IDENTITY),
        ("Aviation", "ryanair", IDENTITY),
        ("Aviation", "jet2", IDENTITY),
        ("Aviation", "wizz air", IDENTITY),
        ("Aviation", "loganair", IDENTITY),
        ("Aviation", "aer lingus", IDENTITY),
        ("Aviation", "eastern airways", IDENTITY),
        # Bare "rail"/"railway"/"highways" also matches civil-engineering and
        # hardware work (a wind-tunnel test rig, a road resurfacing contract);
        # needs coupling. "transport for" stays identity: it's the UK transport
        # authority naming pattern (Transport for London/Wales/...), not
        # generic vocabulary.
        ("Rail and Transport", "rail", GENERIC),
        ("Rail and Transport", "railway", GENERIC),
        ("Rail and Transport", "highways", GENERIC),
        ("Rail and Transport", "transport for", IDENTITY),
        ("Rail and Transport", "network rail", IDENTITY),
        ("Rail and Transport", "tfl", IDENTITY),
        ("Rail and Transport", "avanti west coast", IDENTITY),
        ("Rail and Transport", "lner", IDENTITY),
        ("Rail and Transport", "crosscountry", IDENTITY),
        ("Rail and Transport", "southeastern", IDENTITY),
        ("Rail and Transport", "south western railway", IDENTITY),
        ("Rail and Transport", "thameslink", IDENTITY),
        ("Rail and Transport", "greater anglia", IDENTITY),
        ("Rail and Transport", "chiltern railways", IDENTITY),
        ("Rail and Transport", "transpennine express", IDENTITY),
        ("Rail and Transport", "west midlands railway", IDENTITY),
        ("Rail and Transport", "merseyrail", IDENTITY),
        ("Rail and Transport", "scotrail", IDENTITY),
        ("Rail and Transport", "arriva rail", IDENTITY),
        ("Rail and Transport", "docklands light railway", IDENTITY),
        ("Rail and Transport", "eurostar", IDENTITY),
        ("Rail and Transport", "high speed 2", IDENTITY),
        # Bare "energy"/"grid"/"utilities"/"electricity" also matches
        # non-IT work (steel fittings, electrical installation, lab
        # consumables, academy-trust electricity supply contracts); needs
        # coupling. "national grid"/"ofgem"/"smart meter" etc. are specific
        # enough to stay identity.
        ("Energy", "energy", GENERIC),
        ("Energy", "grid", GENERIC),
        ("Energy", "utilities", GENERIC),
        ("Energy", "electricity", GENERIC),
        ("Energy", "national grid", IDENTITY),
        ("Energy", "ofgem", IDENTITY),
        ("Energy", "smart meter", IDENTITY),
        ("Energy", "power distribution", IDENTITY),
        ("Energy", "power networks", IDENTITY),
        ("Energy", "sse plc", IDENTITY),  # not bare "sse": collides with "proce-sse-s", "e-sse-ntial" etc.
        ("Energy", "scottish power", IDENTITY),
        ("Energy", "centrica", IDENTITY),
        ("Energy", "cadent", IDENTITY),
        ("Energy", "npower", IDENTITY),
        ("Energy", "british gas", IDENTITY),
        ("Energy", "northern powergrid", IDENTITY),
        ("Energy", "western power distribution", IDENTITY),
        ("Energy", "electricity north west", IDENTITY),
        ("Energy", "ssen transmission", IDENTITY),  # not bare "ssen": collides with "e-ssen-tial"
        ("Energy", "drax", IDENTITY),
]


def seed_sector_keywords(conn: sqlite3.Connection) -> None:
    if not _table_empty(conn, "config_sector_keywords"):
        return
    conn.executemany(
        "INSERT INTO config_sector_keywords (sector, keyword, category, notes) VALUES (?, ?, ?, NULL)",
        SECTOR_KEYWORDS,
    )
    conn.commit()


def seed_gate2_terms(conn: sqlite3.Connection) -> None:
    if not _table_empty(conn, "config_gate2_terms"):
        return
    rows = [
        ("hardware", "fail", None),
        ("packaged product", "fail", None),
        ("managed service", "fail", None),
        ("resale", "fail", None),
        ("bespoke build", "unconditional_pass", None),
        ("integration", "unconditional_pass", None),
        (
            "platform",
            "generic_needs_coupling",
            "Named in the Keyword Set reference as a past flooding cause "
            "(Legacy Infrastructure Support, Digital Experience Platform).",
        ),
        ("digital", "generic_needs_coupling", None),
        ("data", "generic_needs_coupling", None),
    ]
    conn.executemany(
        "INSERT INTO config_gate2_terms (term, category, notes) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()


def seed_coupling_terms(conn: sqlite3.Connection) -> None:
    if not _table_empty(conn, "config_coupling_terms"):
        return
    sector_rows = [
        ("real-time payments", "Fintech"),
        ("payments platform", "Fintech"),
        ("digital wallet", "Fintech"),
        ("open banking", "Fintech"),
        ("clearing and settlement", "Fintech"),
        ("banking api", "Fintech"),
        ("systems assurance", "Fintech"),
        ("fintech", "Fintech"),
        ("airline booking system", "Aviation"),
        ("airline operations software", "Aviation"),
        ("flight operations platform", "Aviation"),
        ("passenger service system", "Aviation"),
        ("airline", "Aviation"),
        ("signalling software", "Rail and Transport"),
        ("ticketing system", "Rail and Transport"),
        ("passenger information system", "Rail and Transport"),
        ("real-time data platform", "Rail and Transport"),
        ("train control software", "Rail and Transport"),
        ("rail", "Rail and Transport"),
        ("transport", "Rail and Transport"),
        ("smart grid", "Energy"),
        ("iot telemetry", "Energy"),
        ("energy monitoring software", "Energy"),
        ("grid data platform", "Energy"),
        ("smart metering software", "Energy"),
        ("energy", "Energy"),
        ("utility", "Energy"),
    ]
    capability_rows = [
        "corax",
        "tiris",
        "erlang",
        "elixir",
        "digital identity",
        "distributed systems",
        "fault-tolerant",
        "high-resilience",
        "devops",
        "cloud engineering",
        "vision ai",
        "security-aware engineering",
        "architecture",
        "integration design",
        # From Kanvesh, 2026-07-28. Several of these are single broad words
        # (data, digital, secure, security, application, development, agile,
        # software, identity) that will match a lot of unrelated text as
        # substrings -- worth watching for false-positive coupling the way
        # "platform"/"digital"/"data" alone already needed watching for in
        # Gate 2 (see config_gate2_terms' generic_needs_coupling notes).
        # Bare "ai" deliberately omitted: matching is plain substring search
        # (no word boundaries), and "ai" matches inside "maintenance",
        # "detail", "email", "chair" etc. -- confirmed live, it wrongly
        # coupled a "grounds maintenance" notice to Fintech via "Some Bank" +
        # "ai" in "maintenance". "artificial intelligence" and "ai services"
        # are long enough phrases to be safe.
        "data",
        "data platform",
        "data engineering",
        "digital",
        "secure",
        "security",
        "secure messaging",
        "application",
        "development",
        "agile",
        "software",
        "software development",
        "artificial intelligence",
        "digital transformation",
        "cloud platform",
        "identity",
        "ai services",
        "agile delivery",
        "api integration",
        "secure communications",
    ]
    conn.executemany(
        "INSERT INTO config_coupling_terms (term, kind, sector, notes) VALUES (?, 'sector', ?, NULL)",
        sector_rows,
    )
    conn.executemany(
        "INSERT INTO config_coupling_terms (term, kind, sector, notes) VALUES (?, 'capability', NULL, NULL)",
        [(term,) for term in capability_rows],
    )
    conn.commit()


def seed_exclusion_terms(conn: sqlite3.Connection) -> None:
    if not _table_empty(conn, "config_exclusion_terms"):
        return
    now = _now()
    rows = [
        ("Aviation", "ground equipment", "Airport/ground-side equipment, not airline software."),
        ("Aviation", "ground handling", "Airport/ground-side services, not airline software."),
        ("Rail and Transport", "track", "Physical track works, not software."),
        ("Rail and Transport", "rolling stock", "Vehicle/hardware procurement, not software."),
        ("Rail and Transport", "station construction", "Civil works, not software."),
        ("Energy", "substation construction", "Civil/electrical works, not software."),
        ("Energy", "cabling", "Physical installation, not software."),
        ("Energy", "boiler servicing", "Maintenance work, not software."),
    ]
    conn.executemany(
        "INSERT INTO config_exclusion_terms (sector, term, notes, updated_at, updated_by) "
        "VALUES (?, ?, ?, ?, ?)",
        [(sector, term, notes, now, SEEDED_BY) for sector, term, notes in rows],
    )
    conn.commit()
    log_audit(conn, "config", "config_exclusion_terms", "settings_change", SEEDED_BY, "initial seed")


def seed_sector_cpv_scope(conn: sqlite3.Connection) -> None:
    if not _table_empty(conn, "config_sector_cpv_scope"):
        return
    now = _now()
    rows = [
        ("Fintech", ["72", "48"], "Mark's sectors, 2026-07-28: only IT services (72xxx) and software "
         "package (48xxx) CPV codes are in scope; overrides config_cpv_lists for these sectors."),
        ("Aviation", ["72", "48"], "Mark's sectors, 2026-07-28: only IT services (72xxx) and software "
         "package (48xxx) CPV codes are in scope; overrides config_cpv_lists for these sectors."),
        ("Rail and Transport", ["72", "48"], "Mark's sectors, 2026-07-28: only IT services (72xxx) and "
         "software package (48xxx) CPV codes are in scope; overrides config_cpv_lists for these sectors."),
        ("Energy", ["72", "48"], "Mark's sectors, 2026-07-28: only IT services (72xxx) and software "
         "package (48xxx) CPV codes are in scope; overrides config_cpv_lists for these sectors."),
        ("Central and Local Government", ["72", "48"], "Applied 2026-07-29: same restriction as Mark's "
         "sectors -- most of this sector's real notices are non-IT (construction, business services, "
         "etc.), same reasoning, not a misclassification fix."),
        ("NHS and Healthcare", ["72", "48"], "Applied 2026-07-29: same restriction as Mark's sectors -- "
         "most of this sector's real notices are non-IT (clinical services, medical devices, etc.), "
         "same reasoning, not a misclassification fix."),
    ]
    conn.executemany(
        "INSERT INTO config_sector_cpv_scope "
        "(sector, allowed_cpv_prefixes, enabled, notes, updated_at, updated_by) "
        "VALUES (?, ?, 1, ?, ?, ?)",
        [(sector, json.dumps(prefixes), notes, now, SEEDED_BY) for sector, prefixes, notes in rows],
    )
    conn.commit()
    log_audit(conn, "config", "config_sector_cpv_scope", "settings_change", SEEDED_BY, "initial seed")


def seed_framework_keywords(conn: sqlite3.Connection) -> None:
    if not _table_empty(conn, "config_framework_keywords"):
        return
    rows = [
        ("call-off", "call_off"),
        ("call off", "call_off"),
        ("framework call-off", "call_off"),
        ("draw-down", "call_off"),
        ("mini-competition", "call_off"),
        ("mini competition", "call_off"),
        ("framework establishment", "establishment"),
        ("establish a framework", "establishment"),
        ("framework entry", "establishment"),
        ("join the framework", "establishment"),
        ("direct award", "direct"),
        ("open procurement", "direct"),
        ("open tender", "direct"),
        ("restricted procedure", "direct"),
        ("competitive procedure with negotiation", "direct"),
    ]
    conn.executemany(
        "INSERT INTO config_framework_keywords (term, category, notes) VALUES (?, ?, NULL)",
        rows,
    )
    conn.commit()


def seed_trifork_frameworks(conn: sqlite3.Connection) -> None:
    # Intentionally empty: no confirmed UK framework access as of the
    # references (G-Cloud 15 application in progress). Any detected
    # call-off therefore fails until a row is added here.
    return


def seed_cpv_lists(conn: sqlite3.Connection) -> None:
    if not _table_empty(conn, "config_cpv_lists"):
        return
    rows = [
        ("72200000", "PASS", None, None),
        ("72212000", "PASS", None, None),
        ("72250000", "PASS", None, None),
        ("72263000", "PASS", None, None),
        ("72310000", "PASS", None, None),
        ("72400000", "PASS", None, None),
        ("72500000", "PASS", None, None),
        ("72", "INFERRED_FIT", None, "Adjacent 72xxx not on the explicit PASS list."),
        ("73", "INFERRED_FIT", None, "Adjacent 73xxx, subject to the 73430000 exact FAIL below."),
        (
            "48",
            "FLAG",
            None,
            "Open question: Trifork as product vendor for Corax and Tiris. Never auto-fail, never clean pass.",
        ),
        ("33", "FAIL", None, None),
        ("32", "FAIL", None, None),
        ("45", "FAIL", None, None),
        ("66", "FAIL", None, None),
        ("50", "FAIL", None, None),
        ("73430000", "FAIL", None, None),
        ("80420000", "FAIL", "security testing", "Fails only when bundled with secure testing."),
        ("48190000", "FAIL", "testing", "Fails only when bundled with testing."),
    ]
    conn.executemany(
        "INSERT INTO config_cpv_lists (cpv_code, list_type, condition_keyword, notes) "
        "VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    log_audit(
        conn,
        "config",
        "config_cpv_lists",
        "settings_change",
        SEEDED_BY,
        "initial seed, sourced from the Kanvesh scouting skill Section 4, "
        "verified against Home Office SCBP notice 039639-2026",
    )


def seed_scale_filter(conn: sqlite3.Connection) -> None:
    if not _table_empty(conn, "config_scale_filter"):
        return
    now = _now()
    si_primes = [
        "IBM",
        "Capgemini",
        "Accenture",
        "Atos",
        "Capita",
        "Leidos",
        "BAE Systems AI",
        "CGI",
        "Cognizant",
    ]
    conn.execute(
        "INSERT INTO config_scale_filter "
        "(enabled, value_threshold, si_prime_suppliers, agreed_date, notes, updated_at, updated_by) "
        "VALUES (1, 500000000, ?, '2026-06-15', ?, ?, ?)",
        (
            json.dumps(si_primes),
            "Separately agreed rule (15 June 2026), distinct from the "
            "no-minimum-value-floor non-negotiable. Toggle 'enabled' to 0 to "
            "disable without deleting the rule.",
            now,
            SEEDED_BY,
        ),
    )
    conn.commit()
    log_audit(conn, "config", "config_scale_filter", "settings_change", SEEDED_BY, "initial seed")


CAPABILITY_PROFILE_TEXT = """Trifork UK / Erlang Solutions core capability: high-resilience, \
fault-tolerant distributed systems (Erlang/Elixir), built for scale and mission-critical \
reliability (telecoms-grade DNA).

Four capability areas (test capability match against these, not general narrative language \
like "AI", "data" or "platform" alone):
- Strategy, Discovery and Leadership: strategic advisory, design/discovery, programme leadership
- Engineering and Integration: backend, API, cloud engineering, architecture, integration design
- Platforms, Data and Operations: platform engineering, DevOps, infrastructure, data engineering
- Advanced Technology and Assurance: AI/ML, Vision AI, QA, test strategy, security-aware engineering

Key products:
- Corax AI and Data Platform: data engineering, AI integration, analytics
- Tiris secure messaging: high-security comms (relevant to security-sensitive buyers, \
e.g. Home Office, policing)
- Erlang Solutions engineering: high-resilience functional programming for mission-critical systems
- Digital identity capability: secure authentication patterns
- Sovereign hosting via Danish data centres: reference architecture only, never a match for a \
UK data-residency or clearance requirement

Strongest track record: Fintech (payments, real-time transactions, e.g. Klarna, Visa, Vocalink, \
Danske Bank). Aviation, Rail and Transport and Energy are transferable-capability plays, not \
proven-sector plays; match on engineering fit, not sector history.

Known capability gaps (load-bearing, check before any HIGH or MED rating):
- No confirmed UK Security Clearance population (SC or DV)
- No UK central government reference contracts, European proof points only
- No UK framework access as of this profile's date (G-Cloud 15 application in progress)
- Approximately 15 staff, GBP 3 million turnover; scale is a constraint on large lots

If a notice's core requirement isn't covered by anything above, don't invent a stretch fit. \
Flag it and describe the gap plainly."""


def seed_capability_profile(conn: sqlite3.Connection) -> None:
    if not _table_empty(conn, "config_capability_profile"):
        return
    now = _now()
    conn.execute(
        "INSERT INTO config_capability_profile (profile_text, updated_at, updated_by) "
        "VALUES (?, ?, ?)",
        (CAPABILITY_PROFILE_TEXT, now, SEEDED_BY),
    )
    conn.commit()
    log_audit(
        conn,
        "config",
        "config_capability_profile",
        "settings_change",
        SEEDED_BY,
        "initial seed, sourced from the Capability Reference doc",
    )


def seed_sources(conn: sqlite3.Connection) -> None:
    if not _table_empty(conn, "config_sources"):
        return
    now = _now()
    rows = [
        (
            "Find a Tender",
            "find_a_tender",
            "https://www.find-tender.service.gov.uk/api/1.0",
            1,
            "UK-wide, above-threshold notices. Public OCDS API, no auth.",
        ),
        (
            "Contracts Finder",
            "contracts_finder",
            "https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search",
            1,
            "England, below-threshold notices. Public OCDS API, no auth.",
        ),
        (
            "Contracts Finder (CSV)",
            "contracts_finder_csv",
            "https://www.contractsfinder.service.gov.uk",
            1,
            "Same underlying site as 'Contracts Finder' above, via its own "
            "CSV export instead of the OCDS API -- confirmed live 2026-08-10 "
            "that several genuine, live opportunities (incl. ones syndicated "
            "through third-party portals) are structurally absent from the "
            "OCDS feed but present here. Runs alongside the OCDS sweep, not "
            "instead of it; writes the same source name (\"Contracts "
            "Finder\") into notices.source so both feeds appear as one row "
            "on the Overview's Notices by Source table.",
        ),
        (
            "Public Contracts Scotland",
            "public_contracts_scotland",
            "https://api.publiccontractsscotland.gov.uk/v1",
            1,
            "Public OCDS API, no auth. Queried per-month, not date-range paginated "
            "like Find a Tender/Contracts Finder.",
        ),
        (
            "Sell2Wales",
            "sell2wales",
            "https://api.sell2wales.gov.wales/v1",
            1,
            "Public OCDS API, no auth. Same platform/shape as Public Contracts "
            "Scotland. As of 2026-07-28 the live API intermittently 500s on its "
            "own end (a server-side 'nvarchar to float' bug, not our request) --"
            " sweep retries with backoff and skips the source for that run if it "
            "keeps failing.",
        ),
        (
            "eTendersNI",
            "etendersni",
            "https://etendersni.gov.uk/epps",
            0,
            "NOT IMPLEMENTED -- disabled by default, and not just a missing "
            "scraper. Confirmed live (incl. via headless-browser rendering) "
            "that the only search form returning results requires solving a "
            "mandatory CAPTCHA -- a deliberate anti-automation control we "
            "won't attempt to bypass. Sweeping this source needs a legitimate "
            "data-sharing arrangement with NI's Central Procurement "
            "Directorate, not a scraper. Enabling this row does nothing.",
        ),
    ]
    conn.executemany(
        "INSERT INTO config_sources (name, source_type, base_url, enabled, notes, updated_at, updated_by) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(name, source_type, base_url, enabled, notes, now, SEEDED_BY) for name, source_type, base_url, enabled, notes in rows],
    )
    conn.commit()
    log_audit(conn, "config", "config_sources", "settings_change", SEEDED_BY, "initial seed")


def seed_all(conn: sqlite3.Connection) -> None:
    seed_owner_map(conn)
    seed_sector_keywords(conn)
    seed_gate2_terms(conn)
    seed_coupling_terms(conn)
    seed_framework_keywords(conn)
    seed_trifork_frameworks(conn)
    seed_cpv_lists(conn)
    seed_scale_filter(conn)
    seed_capability_profile(conn)
    seed_sources(conn)
    seed_exclusion_terms(conn)
    seed_sector_cpv_scope(conn)

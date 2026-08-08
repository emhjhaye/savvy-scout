"""Shared "in scope" definition (2026-07-30), used consistently across the
Overview, Opportunities list/pills, sidebar Workflow Stages counts, and topbar
notifications: a notice counts as in scope when it has a real sector, its UK
stage is UK1-UK4 (excludes UK5/awarded and unrecognised stages), and its CPV
is within that sector's configured scope (config_sector_cpv_scope). Built from
that table at request time, not hardcoded, so it stays correct if a sector's
allowed prefixes are edited in the admin screen.

One place, so "in scope" means the same thing everywhere it's used, rather
than each view drifting into its own slightly different definition."""

import json
import sqlite3

IN_SCOPE_UK_STAGES = ("UK1", "UK2", "UK3", "UK4")


def in_scope_filter_sql(conn: sqlite3.Connection) -> tuple[str, list]:
    rows = conn.execute(
        "SELECT sector, allowed_cpv_prefixes FROM config_sector_cpv_scope WHERE enabled = 1"
    ).fetchall()
    stage_placeholders = ",".join("?" for _ in IN_SCOPE_UK_STAGES)
    params: list = list(IN_SCOPE_UK_STAGES)

    if not rows:
        # No sector has a CPV scope configured -- just the sector/stage rule.
        return f"sector IS NOT NULL AND uk_stage IN ({stage_placeholders})", params

    sector_clauses = []
    for row in rows:
        prefixes = json.loads(row["allowed_cpv_prefixes"])
        prefix_conds = " OR ".join("cpv_primary LIKE ?" for _ in prefixes)
        sector_clauses.append(f"(sector = ? AND ({prefix_conds}))")
        params.append(row["sector"])
        params.extend(f"{p}%" for p in prefixes)

    where = f"uk_stage IN ({stage_placeholders}) AND ({' OR '.join(sector_clauses)})"
    # IN_SCOPE_UK_STAGES params must come first to match the f-string above.
    return where, params

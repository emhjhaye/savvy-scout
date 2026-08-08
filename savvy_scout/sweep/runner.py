"""Orchestrates a full sweep: pull from every enabled config_sources row,
dedupe/upsert, run the expiry radar on award notices, then triage every
notice still in NEW status."""

import logging
import sqlite3

from savvy_scout.config import Settings
from savvy_scout.sweep.dedupe import upsert_notice
from savvy_scout.sweep.expiry_radar import surface_if_expiring
from savvy_scout.sources.contracts_finder import sweep_contracts_finder
from savvy_scout.sources.etendersni import sweep_etendersni
from savvy_scout.sources.find_a_tender import sweep_find_a_tender
from savvy_scout.sources.public_contracts_scotland import sweep_public_contracts_scotland
from savvy_scout.sources.sell2wales import sweep_sell2wales
from savvy_scout.triage.gates import triage_notice

logger = logging.getLogger(__name__)

# Dispatch key (config_sources.source_type) -> client function. Every client
# function has the same (base_url, lookback_days) -> Iterator[ParsedNotice]
# shape so a new source only needs a row here plus a config_sources entry --
# no changes to run_sweep itself.
SOURCE_REGISTRY = {
    "find_a_tender": sweep_find_a_tender,
    "contracts_finder": sweep_contracts_finder,
    "public_contracts_scotland": sweep_public_contracts_scotland,
    "sell2wales": sweep_sell2wales,
    "etendersni": sweep_etendersni,
}


def run_sweep(conn: sqlite3.Connection, settings: Settings) -> dict[str, int]:
    stats = {"pulled": 0, "expiring_leads": 0, "triaged": 0}

    source_rows = conn.execute(
        "SELECT name, source_type, base_url FROM config_sources WHERE enabled = 1"
    ).fetchall()

    for row in source_rows:
        sweep_fn = SOURCE_REGISTRY.get(row["source_type"])
        if sweep_fn is None:
            logger.warning(
                "Skipping sweep source %r: unrecognised source_type %r",
                row["name"], row["source_type"],
            )
            continue
        try:
            for parsed in sweep_fn(row["base_url"], settings.lookback_days):
                upsert_notice(conn, parsed)
                stats["pulled"] += 1
                if surface_if_expiring(conn, parsed):
                    stats["expiring_leads"] += 1
        except Exception:
            logger.exception("Sweep source %r failed; continuing with remaining sources", row["name"])

    stats["triaged"] = triage_pending(conn)
    return stats


def triage_pending(conn: sqlite3.Connection) -> int:
    """Triages every notice still sitting in NEW status. Separated from
    run_sweep so the regression tool (A5) can re-triage notices already in
    the database without re-hitting the live APIs.

    PASS, FLAG and MAYBE headline outcomes all route straight to PHASE2_SCOPED
    for the automated Phase 2 scope read, bypassing the Phase 1 owner queue
    entirely (only FAIL lands in AWAITING_PHASE1_APPROVAL, for an owner
    double-check). A FLAG/MAYBE notice does not auto-escalate to Victoria at
    this point: the owner sees the Gate 1 flag alongside the Phase 2 AI read
    once it reaches AWAITING_PHASE2_APPROVAL, and marks it for Victoria's
    decision themselves (see workflow.approvals.mark_victoria_decision)."""
    pending_ids = [
        row["id"] for row in conn.execute("SELECT id FROM notices WHERE status = 'NEW'").fetchall()
    ]
    triaged = 0
    for notice_id in pending_ids:
        try:
            triage_notice(conn, notice_id)
            triaged += 1
        except Exception:
            # One bad notice (a transient DB lock conflict, a data edge case)
            # must not strand every notice after it in NEW -- caught here so
            # the daily sweep never silently leaves a growing backlog behind
            # a single failure (2026-07-30: found ~289 stuck this way after
            # the scheduled sweep ran alongside other DB activity).
            logger.exception("Triage failed for notice %s; continuing with remaining notices", notice_id)
    return triaged

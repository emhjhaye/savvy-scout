"""Append-only audit log helper. Every status change, approval, rejection and
settings change is logged with user, timestamp and reason (SPEC.md non-negotiable 7)."""

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_audit(
    conn: sqlite3.Connection,
    entity_type: str,
    entity_id: str,
    action: str,
    user: str,
    reason: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        "INSERT INTO audit_log (entity_type, entity_id, action, user, timestamp, reason, detail) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            entity_type,
            entity_id,
            action,
            user,
            _now(),
            reason,
            json.dumps(detail) if detail is not None else None,
        ),
    )
    conn.commit()


def log_status_change(
    conn: sqlite3.Connection,
    notice_id: int,
    from_status: str | None,
    to_status: str,
    changed_by: str,
    reason: str | None = None,
) -> None:
    now = _now()
    conn.execute(
        "INSERT INTO status_history (notice_id, from_status, to_status, changed_by, changed_at, reason) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (notice_id, from_status, to_status, changed_by, now, reason),
    )
    conn.commit()
    log_audit(
        conn,
        "notice",
        str(notice_id),
        "status_change",
        changed_by,
        reason,
        {"from": from_status, "to": to_status},
    )

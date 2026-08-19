"""Daily database backup. Wired to Windows Task Scheduler, see README."""

import os
import shutil
from datetime import datetime
from pathlib import Path

# SAVVY_SCOUT_BACKUPS_DIR lets a production deploy (Render's persistent
# disk, e.g. /var/data/backups) point backups somewhere that actually
# survives a redeploy -- the default keeps local dev unchanged.
DEFAULT_BACKUPS_DIR = os.environ.get("SAVVY_SCOUT_BACKUPS_DIR", "backups")

# 2026-08-19 incident: backups were never pruned, so the persistent disk
# (1 GB on Render) silently filled to 100% after 12 days of accumulated
# daily snapshots, breaking every DB write in the live app (including
# login) until the oldest backups were manually deleted. Keep only the
# most recent KEEP_BACKUPS from here on.
KEEP_BACKUPS = int(os.environ.get("SAVVY_SCOUT_KEEP_BACKUPS", "7"))


def _prune_old_backups(backup_dir: Path, stem: str, suffix: str, keep: int) -> None:
    existing = sorted(
        backup_dir.glob(f"{stem}_*{suffix}"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for stale in existing[keep:]:
        stale.unlink(missing_ok=True)


def backup_database(db_path: str, backup_dir: str = DEFAULT_BACKUPS_DIR, keep: int = KEEP_BACKUPS) -> str:
    source = Path(db_path)
    if not source.exists():
        raise FileNotFoundError(f"Database not found at {db_path}")

    dest_dir = Path(backup_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = dest_dir / f"{source.stem}_{stamp}{source.suffix}"
    shutil.copy2(source, dest)
    _prune_old_backups(dest_dir, source.stem, source.suffix, keep)
    return str(dest)

"""Daily database backup. Wired to Windows Task Scheduler, see README."""

import os
import shutil
from datetime import datetime
from pathlib import Path

# SAVVY_SCOUT_BACKUPS_DIR lets a production deploy (Render's persistent
# disk, e.g. /var/data/backups) point backups somewhere that actually
# survives a redeploy -- the default keeps local dev unchanged.
DEFAULT_BACKUPS_DIR = os.environ.get("SAVVY_SCOUT_BACKUPS_DIR", "backups")


def backup_database(db_path: str, backup_dir: str = DEFAULT_BACKUPS_DIR) -> str:
    source = Path(db_path)
    if not source.exists():
        raise FileNotFoundError(f"Database not found at {db_path}")

    dest_dir = Path(backup_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = dest_dir / f"{source.stem}_{stamp}{source.suffix}"
    shutil.copy2(source, dest)
    return str(dest)

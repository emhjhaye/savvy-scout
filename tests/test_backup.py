import os
import time
from pathlib import Path

from savvy_scout.db.backup import _prune_old_backups, backup_database


def test_backup_creates_a_timestamped_copy(tmp_path):
    db_path = tmp_path / "savvy_scout.db"
    db_path.write_bytes(b"fake db content")
    backup_dir = tmp_path / "backups"

    dest = backup_database(str(db_path), str(backup_dir))

    assert Path(dest).exists()
    assert list(backup_dir.glob("savvy_scout_*.db")) == [Path(dest)]


def test_prune_old_backups_keeps_only_the_most_recent(tmp_path):
    """Regression (2026-08-19): backups were never pruned, silently filling
    the persistent disk to 100% over 12 days and breaking every DB write in
    the live app, including login, until the oldest ones were deleted by
    hand. Only the most recent `keep` copies should survive."""
    backup_dir = tmp_path
    now = time.time()
    paths = []
    for i in range(5):
        path = backup_dir / f"savvy_scout_2026081{i}_054500.db"
        path.write_bytes(b"snapshot")
        os.utime(path, (now + i, now + i))  # oldest (i=0) to newest (i=4)
        paths.append(path)

    _prune_old_backups(backup_dir, "savvy_scout", ".db", keep=3)

    remaining = set(backup_dir.glob("savvy_scout_*.db"))
    assert remaining == {paths[2], paths[3], paths[4]}


def test_prune_old_backups_only_touches_matching_stem(tmp_path):
    backup_dir = tmp_path
    now = time.time()
    for i in range(4):
        path = backup_dir / f"savvy_scout_2026081{i}_054500.db"
        path.write_bytes(b"snapshot")
        os.utime(path, (now + i, now + i))
    other = backup_dir / "unrelated_file.txt"
    other.write_bytes(b"leave me alone")

    _prune_old_backups(backup_dir, "savvy_scout", ".db", keep=1)

    assert other.exists()
    assert len(list(backup_dir.glob("savvy_scout_*.db"))) == 1


def test_backup_database_prunes_after_writing_new_copy(tmp_path):
    db_path = tmp_path / "savvy_scout.db"
    db_path.write_bytes(b"v1")
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    now = time.time()
    for i in range(6):
        stale = backup_dir / f"savvy_scout_2026080{i}_054500.db"
        stale.write_bytes(b"old snapshot")
        os.utime(stale, (now - 100 + i, now - 100 + i))

    backup_database(str(db_path), str(backup_dir), keep=3)

    assert len(list(backup_dir.glob("savvy_scout_*.db"))) == 3

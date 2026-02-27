import contextlib
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fncli import cli

from . import config
from .core.errors import LifeError

_SKIP_TABLES = {"_migrations"}
_MIN_ROW_RATIO = 0.5
_KEEP_DAILY_DAYS = 30
_KEEP_HOURLY_HOURS = 48


def _is_core_table(name: str) -> bool:
    return name not in _SKIP_TABLES and not ("_fts" in name or name.startswith("fts_"))


def _is_snapshot_dir(p: Path) -> bool:
    return p.is_dir() and p.name[:8].isdigit() and "_" in p.name


def _sqlite_backup(src: Path, dst: Path) -> None:
    src_conn = sqlite3.connect(src, timeout=30)
    dst_conn = sqlite3.connect(dst)
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()


def _row_counts(db_path: Path) -> dict[str, int]:
    try:
        conn = sqlite3.connect(str(db_path), timeout=2)
        try:
            tables = [
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
                if _is_core_table(row[0])
            ]
            counts = {}
            for table in tables:
                with contextlib.suppress(sqlite3.OperationalError):
                    counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
            return counts
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        return {}


def _get_previous_backup(current_path: Path) -> Path | None:
    backup_dir = config.BACKUP_DIR
    if not backup_dir.exists():
        return None
    snapshots = sorted(
        (s for s in backup_dir.iterdir() if _is_snapshot_dir(s)),
        reverse=True,
    )
    for s in snapshots:
        if s == current_path:
            continue
        if (s / "life.db").exists():
            return s / "life.db"
    return None


def _validate_backup(dst: Path, src: Path) -> tuple[bool, str]:
    dst_counts = _row_counts(dst)
    src_counts = _row_counts(src)

    if not dst_counts and src_counts:
        return False, "backup has no rows but source does"

    dst_total = sum(dst_counts.values())
    src_total = sum(src_counts.values())

    if src_total > 0 and dst_total < src_total * _MIN_ROW_RATIO:
        return False, f"backup has {dst_total} rows vs source {src_total} — too much loss"

    for table, src_count in src_counts.items():
        dst_count = dst_counts.get(table, 0)
        if src_count > 0 and dst_count == 0:
            return False, f"table {table} has {src_count} rows in source but 0 in backup"

    return True, "ok"


def run_backup() -> dict[str, Any]:
    src = config.DB_PATH
    if not src.exists():
        return {
            "path": None,
            "integrity_ok": False,
            "rows": 0,
            "delta_total": None,
            "delta_by_table": {},
            "error": "source db missing",
        }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = config.BACKUP_DIR / timestamp
    backup_path.mkdir(parents=True, exist_ok=True)

    dst = backup_path / "life.db"
    _sqlite_backup(src, dst)

    for suffix in ["-shm", "-wal"]:
        wal = src.parent / f"{src.stem}{suffix}"
        if wal.exists():
            shutil.copy2(wal, backup_path / wal.name)

    try:
        conn = sqlite3.connect(str(dst), timeout=2)
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()[0]
            integrity_ok = result == "ok"
        finally:
            conn.close()
    except Exception:
        integrity_ok = False

    if not integrity_ok:
        shutil.rmtree(backup_path, ignore_errors=True)
        return {
            "path": None,
            "integrity_ok": False,
            "rows": 0,
            "delta_total": None,
            "delta_by_table": {},
            "error": "backup failed integrity check",
        }

    valid, reason = _validate_backup(dst, src)
    if not valid:
        shutil.rmtree(backup_path, ignore_errors=True)
        return {
            "path": None,
            "integrity_ok": False,
            "rows": 0,
            "delta_total": None,
            "delta_by_table": {},
            "error": reason,
        }

    current_counts = _row_counts(dst)
    total = sum(current_counts.values())

    previous_db = _get_previous_backup(backup_path)
    if previous_db and previous_db.exists():
        prev_counts = _row_counts(previous_db)
        prev_total = sum(prev_counts.values())
        delta_total = total - prev_total
        delta_by_table = {
            t: current_counts[t] - prev_counts.get(t, 0)
            for t in current_counts
            if current_counts[t] - prev_counts.get(t, 0) != 0
        }
    else:
        delta_total = None
        delta_by_table = {}

    return {
        "path": backup_path,
        "integrity_ok": integrity_ok,
        "rows": total,
        "delta_total": delta_total,
        "delta_by_table": delta_by_table,
    }


def run_prune(
    keep_daily_days: int = _KEEP_DAILY_DAYS, keep_hourly_hours: int = _KEEP_HOURLY_HOURS
) -> int:
    backup_dir = config.BACKUP_DIR
    if not backup_dir.exists():
        return 0

    snapshots = sorted(
        (s for s in backup_dir.iterdir() if _is_snapshot_dir(s)),
        reverse=True,
    )
    if len(snapshots) <= 1:
        return 0

    now = datetime.now()
    hourly_cutoff = now - timedelta(hours=keep_hourly_hours)
    daily_cutoff = now - timedelta(days=keep_daily_days)

    keep: set[Path] = set()
    keep.add(snapshots[0])

    seen_hours: set[str] = set()
    seen_days: set[str] = set()

    for s in snapshots:
        try:
            parts = s.name.split("_")
            date_part = parts[0]
            time_part = parts[1] if len(parts) > 1 else "000000"
            ts = datetime.strptime(f"{date_part}_{time_part}", "%Y%m%d_%H%M%S")
        except (ValueError, IndexError):
            keep.add(s)
            continue

        if ts >= hourly_cutoff:
            hour_key = ts.strftime("%Y%m%d_%H")
            if hour_key not in seen_hours:
                seen_hours.add(hour_key)
                keep.add(s)
        elif ts >= daily_cutoff:
            day_key = ts.strftime("%Y%m%d")
            if day_key not in seen_days:
                seen_days.add(day_key)
                keep.add(s)

    removed = 0
    for s in snapshots:
        if s not in keep:
            shutil.rmtree(s, ignore_errors=True)
            removed += 1

    return removed


def _print_result(result: dict[str, Any]) -> None:
    if result.get("error"):
        raise LifeError(f"backup failed: {result['error']}")

    path = result["path"]
    rows = result["rows"]
    delta_total = result["delta_total"]
    delta_by_table = result["delta_by_table"]
    delta_str = ""
    if delta_total is not None and delta_total != 0:
        delta_str = f" (+{delta_total})" if delta_total > 0 else f" ({delta_total})"
    print(str(path))
    print(f"  {rows} rows{delta_str}")
    for tbl, delta in sorted(delta_by_table.items(), key=lambda x: abs(x[1]), reverse=True):
        sign = "+" if delta > 0 else ""
        print(f"    {tbl} {sign}{delta}")


@cli("life", name="backup")
def backup() -> None:
    """Create verified database backup"""
    result = run_backup()
    _print_result(result)

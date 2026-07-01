import contextlib
import importlib.util
import json
import logging
import re
import shutil
import sqlite3
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from lifeos.core import config

logger = logging.getLogger(__name__)

MIGRATIONS_TABLE = "_migrations"

MigrationFn = Callable[[sqlite3.Connection], None]
Migration = tuple[str, str | MigrationFn]

_LEGACY_MIGRATIONS = {
    "001_foundation",
    "002_subtasks",
    "003_completed_datetime",
    "004_scheduled_time",
    "005_blocked_by",
    "006_task_mutations",
    "007_due_time",
    "008_interventions",
    "009_mutation_reason",
    "010_habit_archived_at",
    "011_deleted_tasks",
    "012_task_links",
    "013_task_links_created_at",
    "014_task_description",
    "015_tags_unique_partial_index",
    "016_checks_completed_at",
    "017_search_fts",
    "018_cancelled_tasks",
    "019_patterns",
    "020_steward_sessions",
    "021_steward_observations",
    "022_observation_tags",
    "023_steward_task_field",
    "023_mood_log",
    "024_steward_task_field.sql",
    "024_remove_steward_tag",
    "024_task_source",
    "025_observation_about_date",
    "026_habit_subhabits_and_private",
    "027_pattern_tags",
    "028_scheduled_vs_deadline",
    "029_is_deadline",
    "030_special_dates",
    "031_improvements",
    "032_comms_foundation",
    "033_comms_stateless",
    "034_comms_account_tracking",
    "035_comms_decision_log",
    "036_comms_proposals",
    "037_comms_proposal_corrections",
    "038_comms_proposal_email",
    "039_comms_signal_messages",
    "040_comms_sender_stats",
    "041_comms_snooze",
    "042_achievements",
    "043_learnings",
    "044_telegram_messages",
    "045_unified_messages",
}

_MAX_MIGRATION_BACKUPS = 32
_SELECT_STAR_RE = re.compile(r"INSERT\s+INTO\s+\w+\s+SELECT\s+\*\s+FROM", re.IGNORECASE)
_DESTRUCTIVE_RE = re.compile(r"\b(DROP\s+TABLE|ALTER\s+TABLE\s+\w+\s+RENAME)\b", re.IGNORECASE)


def _schema_sql() -> str:
    return (Path(__file__).parent / "schema.sql").read_text()


def _poison_path(db_path: Path) -> Path:
    return db_path.parent / "migration_poison.json"


def _breadcrumb_path(db_path: Path) -> Path:
    return db_path.parent / "migration_error.json"


def _write_poison(db_path: Path, name: str, error: str) -> None:
    p = _poison_path(db_path)
    p.write_text(json.dumps({"migration": name, "detail": error[:500], "timestamp": datetime.now().isoformat()}))


def _write_breadcrumb(db_path: Path, name: str, error: str) -> None:
    p = _breadcrumb_path(db_path)
    p.write_text(json.dumps({"migration": name, "detail": error[:500], "timestamp": datetime.now().isoformat()}))


def _check_and_restore_breadcrumb(db_path: Path) -> None:
    """On boot, if a prior migration left a breadcrumb (process died mid-restore), auto-restore."""
    crumb = _breadcrumb_path(db_path)
    if not crumb.exists():
        return
    try:
        data = json.loads(crumb.read_text())
    except (json.JSONDecodeError, OSError):
        return

    backup_dir = config.BACKUP_DIR / "migrations"
    backups = (
        sorted(backup_dir.glob(f"{db_path.stem}.*.backup"), key=lambda p: p.stat().st_mtime, reverse=True)
        if backup_dir.exists()
        else []
    )
    if not backups:
        logger.warning(
            "migration breadcrumb found (migration=%s) but no backups — cannot auto-restore", data.get("migration")
        )
        return

    latest = backups[0]
    logger.warning("migration breadcrumb found (migration=%s) — restoring from %s", data.get("migration"), latest)
    _restore_backup(latest, db_path)
    crumb.unlink(missing_ok=True)
    logger.warning("auto-restored %s from backup and cleared breadcrumb", db_path)


def _check_ghost_db(db_path: Path) -> None:
    """Refuse to init a fresh DB when backups exist with data — silent data loss prevention."""
    if not db_path or not db_path.exists():
        return
    backup_dir = config.BACKUP_DIR / "migrations"
    if not backup_dir.exists():
        return
    backups = sorted(backup_dir.glob(f"{db_path.stem}.*.backup"), key=lambda p: p.stat().st_mtime, reverse=True)
    for backup in backups[:3]:
        try:
            with sqlite3.connect(backup, timeout=5) as bconn:
                row = bconn.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name != '_migrations'"
                ).fetchone()
                if row and row[0] > 5:
                    raise SystemExit(
                        f"FATAL: {db_path} appears fresh but backup at {backup} "
                        f"contains {row[0]} tables. Refusing to overwrite — restore from backup first."
                    )
        except (sqlite3.Error, OSError):
            continue


def _create_backup(db_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    mig_dir = config.BACKUP_DIR / "migrations"
    mig_dir.mkdir(parents=True, exist_ok=True)
    backup_path = mig_dir / f"{db_path.stem}.{timestamp}.backup"
    src = sqlite3.connect(db_path, timeout=30)
    dst = sqlite3.connect(backup_path)
    try:
        src.backup(dst)
    except Exception:
        dst.close()
        src.close()
        if backup_path.exists():
            backup_path.unlink()
        raise
    else:
        dst.close()
        src.close()
    _prune_backups(mig_dir, db_path.stem)
    return backup_path


def _prune_backups(backup_dir: Path, stem: str, keep: int = _MAX_MIGRATION_BACKUPS) -> None:
    backups = sorted(backup_dir.glob(f"{stem}.*.backup"))
    for stale in backups[:-keep]:
        with contextlib.suppress(OSError):
            stale.unlink()


def _restore_backup(backup_path: Path, db_path: Path) -> None:
    tmp = db_path.parent / f".{db_path.stem}.restore.tmp"
    try:
        shutil.copy2(backup_path, tmp)
        tmp.replace(db_path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _table_count(conn: sqlite3.Connection, table: str) -> int:
    try:
        return conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    except sqlite3.OperationalError:
        return 0


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


_INTERNAL_TABLES = {"sqlite_sequence"}


def _check_data_loss(conn: sqlite3.Connection, before: dict[str, int], exempt: set[str] | None = None) -> None:
    for table, count in before.items():
        if table in _INTERNAL_TABLES:
            continue
        if exempt and table in exempt:
            continue
        if not _table_exists(conn, table):
            continue
        after = _table_count(conn, table)
        if after < count:
            raise ValueError(f"migration data loss: {table} had {count} rows, now {after}")


def _is_fresh(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name != '_migrations' AND name != 'sqlite_sequence'"
    ).fetchone()
    return row[0] == 0


def load_migrations() -> list[Migration]:
    migrations_dir = Path(__file__).parent / "migrations"
    if not migrations_dir.exists():
        return []
    files = sorted(f for pat in ("[0-9]*.sql", "[0-9]*.py") for f in migrations_dir.glob(pat))
    result: list[Migration] = []
    for f in files:
        if f.suffix == ".sql":
            result.append((f.stem, f.read_text()))
        elif f.suffix == ".py":
            spec = importlib.util.spec_from_file_location(f.stem, f)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore[arg-type]
                if callable(getattr(mod, "up", None)):
                    result.append((f.stem, mod.up))
    return result


def _reject_destructive_sql(name: str, sql: str) -> None:
    if _DESTRUCTIVE_RE.search(sql):
        raise ValueError(
            f"Migration '{name}' contains DROP TABLE or ALTER TABLE RENAME in a string migration. "
            "Use a callable migration (def up(conn)) with explicit transactions."
        )


def _apply_migrations(conn: sqlite3.Connection, db_path: Path) -> None:
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS {MIGRATIONS_TABLE} "
        "(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, "
        "applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.commit()

    if _is_fresh(conn):
        _check_ghost_db(db_path)
        conn.executescript(_schema_sql())
        for name in _LEGACY_MIGRATIONS:
            conn.execute(f"INSERT OR IGNORE INTO {MIGRATIONS_TABLE} (name) VALUES (?)", (name,))
        for name, _ in load_migrations():
            conn.execute(f"INSERT OR IGNORE INTO {MIGRATIONS_TABLE} (name) VALUES (?)", (name,))
        conn.commit()
        return

    # Check and heal breadcrumb from a prior crash mid-restore
    _check_and_restore_breadcrumb(db_path)

    applied = {row[0] for row in conn.execute(f"SELECT name FROM {MIGRATIONS_TABLE}").fetchall()}

    for name in _LEGACY_MIGRATIONS:
        if name not in applied:
            conn.execute(f"INSERT OR IGNORE INTO {MIGRATIONS_TABLE} (name) VALUES (?)", (name,))
    conn.commit()

    applied = {row[0] for row in conn.execute(f"SELECT name FROM {MIGRATIONS_TABLE}").fetchall()}
    pending = [(n, m) for n, m in load_migrations() if n not in applied]

    if not pending:
        return

    # Check poison — a previously failed migration that must not retry without human intervention
    poison = _poison_path(db_path)
    if poison.exists():
        try:
            data = json.loads(poison.read_text())
            poisoned_name = data.get("migration")
            if poisoned_name and any(n == poisoned_name for n, _ in pending):
                raise SystemExit(
                    f"FATAL: migration '{poisoned_name}' previously failed and is poisoned. "
                    f"Detail: {data.get('detail', 'unknown')}. "
                    f"Fix the migration, then delete {poison} to retry."
                )
        except (json.JSONDecodeError, OSError):
            pass

    # One backup for the whole batch — not one per migration
    backup_path: Path | None = None
    if db_path.exists():
        backup_path = _create_backup(db_path)

    try:
        for name, migration in pending:
            tables = [
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name != ? AND name NOT LIKE '%_fts%'",
                    (MIGRATIONS_TABLE,),
                ).fetchall()
            ]
            before = {t: _table_count(conn, t) for t in tables}

            try:
                if callable(migration):
                    _guard_msg = f"Migration '{name}' uses INSERT INTO ... SELECT * — positional column mismatch risk. Use explicit column names."

                    def _guard(sql: str, _msg: str = _guard_msg) -> None:
                        if _SELECT_STAR_RE.search(sql):
                            raise ValueError(_msg)

                    conn.set_trace_callback(_guard)
                    try:
                        migration(conn)
                    finally:
                        conn.set_trace_callback(None)
                else:
                    _reject_destructive_sql(name, migration)
                    conn.executescript(migration)

                _check_data_loss(conn, before)
                conn.execute(f"INSERT OR IGNORE INTO {MIGRATIONS_TABLE} (name) VALUES (?)", (name,))
                conn.commit()
            except Exception as e:
                conn.rollback()
                if backup_path and db_path.exists():
                    _write_breadcrumb(db_path, name, str(e))
                    _restore_backup(backup_path, db_path)
                    _breadcrumb_path(db_path).unlink(missing_ok=True)
                    _write_poison(db_path, name, str(e))
                logger.error("migration '%s' failed — db restored, migration poisoned: %s", name, e)
                raise
    finally:
        # Clean up successful batch backup
        if backup_path and backup_path.exists():
            backup_path.unlink()


def init(db_path: Path | None = None) -> None:
    db_path = db_path or config.DB_PATH
    db_path.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        _apply_migrations(conn, db_path)
    finally:
        conn.close()


def migrate(db_path: Path | None = None) -> None:
    db_path = db_path or config.DB_PATH
    db_path.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        _apply_migrations(conn, db_path)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

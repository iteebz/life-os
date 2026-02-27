import shutil
import sqlite3
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from . import config

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


@contextmanager
def get_db(db_path: Path | None = None):
    db_path = db_path if db_path else config.DB_PATH
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _schema_sql() -> str:
    return (Path(__file__).parent / "schema.sql").read_text()


def _create_backup(db_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    mig_dir = config.BACKUP_DIR / "migrations"
    mig_dir.mkdir(parents=True, exist_ok=True)
    backup_path = mig_dir / f"life.{timestamp}.backup"
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
    return backup_path


def _restore_backup(backup_path: Path, db_path: Path) -> None:
    shutil.copy2(backup_path, db_path)


def _table_count(conn: sqlite3.Connection, table: str) -> int:
    try:
        return conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]  # noqa: S608
    except sqlite3.OperationalError:
        return 0


def _check_data_loss(
    conn: sqlite3.Connection, before: dict[str, int], exempt: set[str] | None = None
) -> None:
    for table, count in before.items():
        if exempt and table in exempt:
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
    return [
        (sql_file.stem, sql_file.read_text())
        for sql_file in sorted(migrations_dir.glob("[0-9]*.sql"))
    ]


def _apply_migrations(conn: sqlite3.Connection, db_path: Path) -> None:
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS {MIGRATIONS_TABLE} "
        "(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.commit()

    if _is_fresh(conn):
        conn.executescript(_schema_sql())
        for name in _LEGACY_MIGRATIONS:
            conn.execute(f"INSERT OR IGNORE INTO {MIGRATIONS_TABLE} (name) VALUES (?)", (name,))  # noqa: S608
        conn.commit()
        return

    applied = {row[0] for row in conn.execute(f"SELECT name FROM {MIGRATIONS_TABLE}").fetchall()}  # noqa: S608

    for name in _LEGACY_MIGRATIONS:
        if name not in applied:
            conn.execute(f"INSERT OR IGNORE INTO {MIGRATIONS_TABLE} (name) VALUES (?)", (name,))  # noqa: S608
    conn.commit()

    applied = {row[0] for row in conn.execute(f"SELECT name FROM {MIGRATIONS_TABLE}").fetchall()}  # noqa: S608
    pending = [(n, m) for n, m in load_migrations() if n not in applied]

    if not pending:
        return

    backup_path: Path | None = None

    for name, migration in pending:
        if db_path.exists() and backup_path is None:
            backup_path = _create_backup(db_path)

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
                migration(conn)
                exempt = None
            else:
                conn.executescript(migration)
                exempt = None

            _check_data_loss(conn, before, exempt=exempt)
            conn.execute(f"INSERT OR IGNORE INTO {MIGRATIONS_TABLE} (name) VALUES (?)", (name,))  # noqa: S608
            conn.commit()
        except Exception:
            conn.rollback()
            if backup_path and db_path:
                _restore_backup(backup_path, db_path)
            raise

    if backup_path and backup_path.exists():
        backup_path.unlink()


def init(db_path: Path | None = None) -> None:
    db_path = db_path if db_path else config.DB_PATH
    db_path.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        _apply_migrations(conn, db_path)
    finally:
        conn.close()


def migrate(db_path: Path | None = None) -> None:
    db_path = db_path if db_path else config.DB_PATH
    db_path.parent.mkdir(exist_ok=True)
    with get_db(db_path) as conn:
        _apply_migrations(conn, db_path)

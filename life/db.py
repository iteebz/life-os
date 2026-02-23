# life/db.py
import inspect
import shutil
import sqlite3
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime
from importlib import import_module
from pathlib import Path
from typing import cast

from fncli import cli

from . import config
from .lib.errors import echo

MIGRATIONS_TABLE = "_migrations"

MigrationFn = Callable[[sqlite3.Connection], None]
Migration = tuple[str, str | MigrationFn]


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


def load_migrations() -> list[Migration]:
    migrations_dir = Path(__file__).parent / "migrations"
    migrations: list[Migration] = []

    if migrations_dir.exists():
        migrations.extend(
            (sql_file.stem, sql_file.read_text())
            for sql_file in sorted(migrations_dir.glob("*.sql"))
        )

    try:
        mig_module = import_module("life.migrations")
        for name, obj in inspect.getmembers(mig_module):
            if name.startswith("migration_") and callable(obj):
                mig_name = name.replace("migration_", "", 1)
                if not any(m[0] == mig_name for m in migrations):
                    fn: MigrationFn = cast(MigrationFn, obj)
                    migrations.append((mig_name, fn))
    except (ImportError, AttributeError):
        pass

    return sorted(migrations, key=lambda x: x[0])


def _apply_migrations(conn: sqlite3.Connection, db_path: Path) -> None:
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS {MIGRATIONS_TABLE} "
        "(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
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


@cli("life db", name="migrate")
def db_migrate():
    """Run pending database migrations"""
    migrate()
    echo("migrations applied")


@cli("life db", name="backup")
def db_backup():
    """Create database backup"""
    from .lib.backup import backup as _backup

    result = _backup()
    path = result["path"]
    rows = result["rows"]
    delta_total = result["delta_total"]
    delta_by_table = result["delta_by_table"]
    delta_str = ""
    if delta_total is not None and delta_total != 0:
        delta_str = f" (+{delta_total})" if delta_total > 0 else f" ({delta_total})"
    echo(str(path))
    echo(f"  {rows} rows{delta_str}")
    for tbl, delta in sorted(delta_by_table.items(), key=lambda x: abs(x[1]), reverse=True):
        sign = "+" if delta > 0 else ""
        echo(f"    {tbl} {sign}{delta}")


@cli("life db", name="health")
def db_health():
    """Check database integrity"""
    from .health import cli as health_cli

    health_cli()

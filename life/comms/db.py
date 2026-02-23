import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from . import config

MIGRATIONS_TABLE = "_migrations"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


@contextmanager
def get_db(db_path: Path | None = None):
    db_path = db_path if db_path else config.DB_PATH
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def load_migrations() -> list[tuple[str, str]]:
    migrations_dir = Path(__file__).parent / "migrations"
    if not migrations_dir.exists():
        return []

    migrations = []
    for sql_file in sorted(migrations_dir.glob("*.sql")):
        name = sql_file.stem
        sql_content = sql_file.read_text()
        migrations.append((name, sql_content))
    return migrations


def backup_db(db_path: Path | None = None) -> Path | None:
    db_path = db_path if db_path else config.DB_PATH

    if not db_path.exists():
        return None

    if db_path.stat().st_size == 0:
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = config.BACKUP_DIR / timestamp
    backup_dir.mkdir(parents=True, exist_ok=True)

    backup_path = backup_dir / db_path.name
    shutil.copy2(db_path, backup_path)

    return backup_path


def init(db_path: Path | None = None):
    db_path = db_path if db_path else config.DB_PATH

    if db_path.exists() and db_path.stat().st_size > 0:
        backup_db(db_path)

    db_path.parent.mkdir(exist_ok=True)
    with get_db(db_path) as conn:
        create_migrations_table_sql = f"""
            CREATE TABLE IF NOT EXISTS {MIGRATIONS_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """
        conn.execute(create_migrations_table_sql)

        applied_migrations = {
            row[0]
            for row in conn.execute(f"SELECT name FROM {MIGRATIONS_TABLE}").fetchall()  # noqa: S608
        }

        for name, sql_content in load_migrations():
            if name not in applied_migrations:
                conn.executescript(sql_content)
                conn.execute(f"INSERT INTO {MIGRATIONS_TABLE} (name) VALUES (?)", (name,))  # noqa: S608

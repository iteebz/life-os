"""Single DB access layer. All domain code imports get_db from here."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

_db_path: Path | None = None


def configure(path: Path) -> None:
    """Set DB path. Called once at startup and in test fixtures."""
    global _db_path
    _db_path = path


@contextmanager
def get_db():
    from life import config  # deferred: avoids import-time dep on config

    path = _db_path or config.DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

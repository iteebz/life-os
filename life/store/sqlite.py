import logging
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger(__name__)

CONN_SLOW_SECS = 0.1


class LifeConnection(sqlite3.Connection):
    """Subclass to allow weak references."""


def connect(db_path: Path) -> sqlite3.Connection:
    start = time.perf_counter()

    conn = sqlite3.connect(
        db_path, check_same_thread=False, timeout=5.0, factory=LifeConnection
    )
    conn.row_factory = sqlite3.Row
    conn.isolation_level = None

    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")

    elapsed = time.perf_counter() - start
    if elapsed > CONN_SLOW_SECS:
        logger.warning("SQLite connection took %.3fs", elapsed)

    return conn


def connect_readonly(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(
        f"file:{db_path}?mode=ro", uri=True, check_same_thread=False, factory=LifeConnection
    )
    conn.row_factory = sqlite3.Row
    conn.isolation_level = None
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

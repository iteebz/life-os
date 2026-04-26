from __future__ import annotations

import contextvars
import json
import logging
import os
import sqlite3
import threading
import time
import weakref
from collections.abc import Callable, Generator
from contextlib import contextmanager, suppress
from dataclasses import fields
from enum import Enum
from pathlib import Path
from typing import Any, ClassVar, Literal, Protocol, get_args, get_origin

from life.core.errors import StoreError, StoreIntegrityError
from life.core.types import Conn
from life.store.sqlite import connect

logger = logging.getLogger(__name__)

_DB_FILE = "life.db"
_local = threading.local()
_all_connections: weakref.WeakSet[sqlite3.Connection] = weakref.WeakSet()
_all_connections_lock = threading.Lock()
_db_path_override: contextvars.ContextVar[Path | None] = contextvars.ContextVar(
    "db_path_override", default=None
)

BEGIN_IMMEDIATE_RETRIES = 3
BEGIN_IMMEDIATE_BACKOFF_SECS = 0.05


def _in_transaction(conn: Any) -> bool:
    in_tx = getattr(conn, "in_transaction", False)
    return in_tx if isinstance(in_tx, bool) else False


def _begin_immediate(conn: Conn) -> None:
    for attempt in range(BEGIN_IMMEDIATE_RETRIES):
        try:
            conn.execute("BEGIN IMMEDIATE")
            return
        except sqlite3.OperationalError as exc:
            if "database is locked" not in str(exc).lower() or attempt == BEGIN_IMMEDIATE_RETRIES - 1:
                raise
            time.sleep(BEGIN_IMMEDIATE_BACKOFF_SECS * (attempt + 1))


def _init_local() -> None:
    if not hasattr(_local, "connections"):
        _local.connections = {}
        _local.migrations_loaded = set()


def _get_cache() -> dict[str, Any]:
    _init_local()
    return _local.connections


def _get_migrations_loaded() -> set[str]:
    _init_local()
    return _local.migrations_loaded


def _life_dir() -> Path:
    env_dir = os.environ.get("LIFE_DIR")
    if env_dir:
        return Path(env_dir)
    return Path.home() / ".life"


class DataclassInstance(Protocol):
    __dataclass_fields__: ClassVar[dict[str, Any]]


_coercion_cache: dict[type, dict[str, Callable[[Any], Any]]] = {}


def _json_load(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            logger.warning("bad JSON, got %r", value[:80])
            return None
    return value


def _build_coercions(cls: type) -> dict[str, Callable[[Any], Any]]:
    from datetime import date, datetime

    coercions: dict[str, Callable[[Any], Any]] = {}
    for f in fields(cls):
        ft = f.type
        origin = get_origin(ft)
        if origin is not None:
            args = get_args(ft)
            non_none = [a for a in args if a is not type(None)]
            if non_none:
                ft = non_none[0]
                origin = get_origin(ft)
        if isinstance(ft, type) and issubclass(ft, Enum):
            coercions[f.name] = ft
        elif ft is bool:
            coercions[f.name] = bool
        elif origin in (list, dict):
            coercions[f.name] = _json_load
        elif ft is datetime:
            coercions[f.name] = lambda v: datetime.fromisoformat(v) if isinstance(v, str) else v
        elif ft is date:
            coercions[f.name] = lambda v: date.fromisoformat(v.split("T")[0]) if isinstance(v, str) else v
    return coercions


def _get_coercions(cls: type) -> dict[str, Callable[[Any], Any]]:
    cached = _coercion_cache.get(cls)
    if cached is not None:
        return cached
    coercions = _build_coercions(cls)
    _coercion_cache[cls] = coercions
    return coercions


def from_row[T: DataclassInstance](row: dict[str, Any] | Any, dataclass_type: type[T]) -> T:
    row_dict: dict[str, Any] = dict(row) if not isinstance(row, dict) else row
    coercions = _get_coercions(dataclass_type)
    kwargs: dict[str, Any] = {}
    for name in dataclass_type.__dataclass_fields__:
        if name in row_dict:
            value = row_dict[name]
            coerce = coercions.get(name)
            kwargs[name] = coerce(value) if coerce is not None and value is not None else value
    return dataclass_type(**kwargs)


class _ConnContext:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def execute(self, sql: str, params: Any = ()) -> sqlite3.Cursor:
        try:
            return self._conn.execute(sql, params)
        except sqlite3.IntegrityError as e:
            raise StoreIntegrityError(str(e)) from e
        except sqlite3.Error as e:
            raise StoreError(str(e)) from e

    @property
    def total_changes(self) -> int:
        return self._conn.total_changes

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)

    def __enter__(self) -> _ConnContext:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> Literal[False]:
        return False


def resolve_db_path() -> Path:
    override = _db_path_override.get()
    if override:
        return override / _DB_FILE if override.is_dir() else override
    db_path = _life_dir() / _DB_FILE
    if os.environ.get("PYTEST_CURRENT_TEST"):
        raise RuntimeError(
            f"TEST LEAKED: write to production DB blocked ({db_path}). "
            "Use tmp_life_dir fixture to isolate DB writes."
        )
    return db_path


def ensure() -> _ConnContext:
    """Get or create a cached DB connection. The single entry point for all DB access."""
    db_path = resolve_db_path()
    cache_key = str(db_path)
    cache = _get_cache()

    if cache_key in cache:
        return _ConnContext(cache[cache_key])

    db_path.parent.mkdir(parents=True, exist_ok=True)

    migrations_loaded = _get_migrations_loaded()
    if cache_key not in migrations_loaded:
        from life.db import _apply_migrations

        conn_raw = connect(db_path)
        try:
            _apply_migrations(conn_raw, db_path)
        finally:
            pass  # don't close — we'll cache it
        cache[cache_key] = conn_raw
        with _all_connections_lock:
            _all_connections.add(conn_raw)
        migrations_loaded.add(cache_key)
        return _ConnContext(conn_raw)

    conn = connect(db_path)
    cache[cache_key] = conn
    with _all_connections_lock:
        _all_connections.add(conn)
    return _ConnContext(conn)


@contextmanager
def transaction() -> Generator[_ConnContext, None, None]:
    conn = ensure()
    if _in_transaction(conn):
        if not hasattr(_local, "savepoint_seq"):
            _local.savepoint_seq = 0
        _local.savepoint_seq += 1
        savepoint = f"sp_{_local.savepoint_seq}"
        conn.execute(f"SAVEPOINT {savepoint}")
        try:
            yield conn
            conn.execute(f"RELEASE SAVEPOINT {savepoint}")
        except Exception:
            conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            conn.execute(f"RELEASE SAVEPOINT {savepoint}")
            raise
        return

    _begin_immediate(conn)
    try:
        yield conn
        if _in_transaction(conn):
            conn.execute("COMMIT")
    except Exception:
        if _in_transaction(conn):
            conn.execute("ROLLBACK")
        raise


def close_all() -> None:
    cache = _get_cache()
    for conn in cache.values():
        with suppress(sqlite3.ProgrammingError):
            conn.close()
    cache.clear()

    with _all_connections_lock:
        for conn in _all_connections:
            with suppress(sqlite3.ProgrammingError):
                conn.close()
        _all_connections.clear()


def set_test_db_path(db_dir: Path | None) -> None:
    _db_path_override.set(db_dir)


def reset_for_testing() -> None:
    _db_path_override.set(None)
    close_all()
    _get_migrations_loaded().clear()
    _coercion_cache.clear()

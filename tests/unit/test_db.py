# tests/unit/test_db.py
import dataclasses
import re
import sqlite3
from pathlib import Path

import pytest

from life import db
from life.core.models import Habit, Task, TaskMutation
from life.db import load_migrations


def test_init_creates_schema(tmp_life_dir):
    """Verify that db.init() creates the database and the expected tables."""
    with db.get_db() as conn:
        cursor = conn.cursor()
        tables = cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = {t[0] for t in tables}
        assert "tasks" in table_names
        assert "habits" in table_names
        assert "checks" in table_names
        assert "tags" in table_names


def test_init_creates_indexes(tmp_life_dir):
    """Verify that db.init() creates the expected indexes."""
    db.init()
    with db.get_db() as conn:
        cursor = conn.cursor()
        indexes = cursor.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        index_names = {i[0] for i in indexes}
        assert "idx_tags_task" in index_names or "idx_tags_habit" in index_names
        assert "idx_checks_date" in index_names


def test_get_db_context_manager(tmp_life_dir):
    """Verify that get_db() provides a valid connection."""
    with db.get_db() as conn:
        assert conn is not None
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        assert result[0] == 1


def test_get_db_auto_commit(tmp_life_dir):
    """Verify that get_db() automatically commits successful transactions."""
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO tasks (id, content, created) VALUES (?, ?, datetime('now'))",
            ("test_id", "test content"),
        )

    with db.get_db() as conn:
        result = conn.execute("SELECT content FROM tasks WHERE id = ?", ("test_id",)).fetchone()
        assert result[0] == "test content"


def test_get_db_auto_rollback(tmp_life_dir):
    """Verify that get_db() automatically rolls back failed transactions."""
    with pytest.raises(sqlite3.IntegrityError):
        with db.get_db() as conn:
            conn.execute("INSERT INTO tasks (id, content) VALUES (?, ?)", ("test_id", None))

    with db.get_db() as conn:
        result = conn.execute("SELECT * FROM tasks WHERE id = ?", ("test_id",)).fetchone()
        assert result is None


def test_db_init(tmp_life_dir):
    db.init()
    assert (tmp_life_dir / "store.db").exists()


_MODEL_TABLE_MAP: dict[type, tuple[str, set[str], set[str]]] = {
    Task: ("tasks", {"tags"}, set()),
    Habit: ("habits", {"tags", "checks"}, set()),
    TaskMutation: ("task_mutations", set(), set()),
}


def test_models_match_schema():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS _migrations "
        "(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    for _name, migration in load_migrations():
        if callable(migration):
            migration(conn)
        else:
            conn.executescript(migration)

    for model_cls, (table, model_excludes, db_excludes) in _MODEL_TABLE_MAP.items():
        db_cols = {
            r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()
        } - db_excludes
        model_fields = {f.name for f in dataclasses.fields(model_cls)} - model_excludes

        missing_in_db = model_fields - db_cols
        missing_in_model = db_cols - model_fields

        assert not missing_in_db, f"{model_cls.__name__} fields not in {table}: {missing_in_db}"
        assert not missing_in_model, (
            f"{table} columns not in {model_cls.__name__}: {missing_in_model}"
        )

    conn.close()


def test_no_phantom_table_references():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS _migrations "
        "(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    for _name, migration in load_migrations():
        if callable(migration):
            migration(conn)
        else:
            conn.executescript(migration)

    tables_in_schema = {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    conn.close()

    sql_keywords = {
        "on",
        "set",
        "where",
        "values",
        "select",
        "delete",
        "insert",
        "replace",
        "group",
        "order",
        "limit",
    }
    known_virtual = {"_migrations", "sqlite_master"}

    src_dir = Path(__file__).parent.parent.parent / "life"
    phantoms = []

    for py_file in src_dir.rglob("*.py"):
        raw = py_file.read_text()
        content = re.sub(r'""".*?"""', "", raw, flags=re.DOTALL)
        content = re.sub(r"'''.*?'''", "", content, flags=re.DOTALL)
        content = re.sub(r"#.*", "", content)
        cte_names = {
            m.group(1) for m in re.finditer(r"WITH\s+([a-z_]\w*)\s+AS", content, re.IGNORECASE)
        }
        cte_names |= {
            m.group(1) for m in re.finditer(r",\s*([a-z_]\w*)\s+AS\s*\(", content, re.IGNORECASE)
        }

        for match in re.finditer(r"(?:FROM|JOIN|INTO|UPDATE)\s+([a-z_][a-z0-9_]*)\b", content):
            name = match.group(1)
            if (
                name not in tables_in_schema
                and name not in sql_keywords
                and name not in cte_names
                and name not in known_virtual
                and not name.startswith("sqlite_")
                and not name.endswith(("_fts", "_new"))
            ):
                phantoms.append((py_file.name, match.group(0)))

    assert not phantoms, "SQL references tables not in schema:\n" + "\n".join(
        f"  {f}: {ctx}" for f, ctx in phantoms
    )

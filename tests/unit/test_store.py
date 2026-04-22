"""Tests for the store layer: ensure(), transaction(), from_row(), query()."""

import pytest

from life.core.errors import NotFoundError, StoreIntegrityError
from life.store.connection import ensure, from_row, transaction
from life.store.query import query


def test_ensure_returns_cached_connection(tmp_life_dir):
    c1 = ensure()
    c2 = ensure()
    assert c1._conn is c2._conn


def test_ensure_works(tmp_life_dir):
    conn = ensure()
    row = conn.execute("SELECT 1").fetchone()
    assert row[0] == 1


def test_transaction_commits(tmp_life_dir):
    with transaction() as conn:
        conn.execute(
            "INSERT INTO tasks (id, content, created) VALUES (?, ?, datetime('now'))",
            ("tx_test", "transaction test"),
        )
    row = ensure().execute("SELECT content FROM tasks WHERE id = ?", ("tx_test",)).fetchone()
    assert row[0] == "transaction test"


def test_transaction_rollback(tmp_life_dir):
    with pytest.raises(StoreIntegrityError):
        with transaction() as conn:
            conn.execute("INSERT INTO tasks (id, content) VALUES (?, ?)", ("bad", None))
    row = ensure().execute("SELECT * FROM tasks WHERE id = ?", ("bad",)).fetchone()
    assert row is None


def test_transaction_nested_savepoints(tmp_life_dir):
    with transaction() as outer:
        outer.execute(
            "INSERT INTO tasks (id, content, created) VALUES (?, ?, datetime('now'))",
            ("outer", "outer task"),
        )
        with pytest.raises(StoreIntegrityError):
            with transaction() as inner:
                inner.execute("INSERT INTO tasks (id, content) VALUES (?, ?)", ("inner_bad", None))
        # outer should still be intact
    row = ensure().execute("SELECT content FROM tasks WHERE id = ?", ("outer",)).fetchone()
    assert row[0] == "outer task"


def test_store_integrity_error(tmp_life_dir):
    with transaction() as conn:
        conn.execute(
            "INSERT INTO tasks (id, content, created) VALUES (?, ?, datetime('now'))",
            ("dup", "first"),
        )
    with pytest.raises(StoreIntegrityError):
        with transaction() as conn:
            conn.execute(
                "INSERT INTO tasks (id, content, created) VALUES (?, ?, datetime('now'))",
                ("dup", "second"),
            )


def test_from_row(tmp_life_dir):
    from dataclasses import dataclass
    from datetime import datetime

    @dataclass
    class Mood:
        id: int
        score: int
        label: str | None
        logged_at: datetime

    with transaction() as conn:
        conn.execute("INSERT INTO moods (score, label) VALUES (?, ?)", (4, "good"))

    row = ensure().execute("SELECT id, score, label, logged_at FROM moods LIMIT 1").fetchone()
    mood = from_row(row, Mood)
    assert mood.score == 4
    assert mood.label == "good"
    assert isinstance(mood.logged_at, datetime)


def test_query_builder(tmp_life_dir):
    from life.core.models import Task

    with transaction() as conn:
        conn.execute(
            "INSERT INTO tasks (id, content, created) VALUES (?, ?, datetime('now'))",
            ("q1", "query test"),
        )

    tasks = query("tasks", Task).where("id = ?", "q1").not_deleted().fetch(ensure())
    assert len(tasks) == 1
    assert tasks[0].content == "query test"


def test_query_count(tmp_life_dir):
    with transaction() as conn:
        for i in range(3):
            conn.execute(
                "INSERT INTO tasks (id, content, created) VALUES (?, ?, datetime('now'))",
                (f"cnt_{i}", f"task {i}"),
            )

    count = query("tasks").where("deleted_at IS NULL").count(ensure())
    assert count == 3


def test_query_get_not_found(tmp_life_dir):
    from life.core.models import Task

    with pytest.raises(NotFoundError):
        query("tasks", Task).not_deleted().get(ensure(), "nonexistent")

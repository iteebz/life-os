import uuid as _uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from life.lib.ids import parse_ref
from life.lib.store import get_db


class _HasId(Protocol):
    @property
    def id(self) -> str: ...


@dataclass(frozen=True)
class StewardSession:
    id: int
    summary: str
    logged_at: datetime
    claude_session_id: str | None = None
    name: str | None = None
    model: str | None = None


@dataclass(frozen=True)
class Observation:
    id: str
    body: str
    tag: str | None
    logged_at: datetime
    about_date: date | None = None


def resolve_prefix[T: _HasId](prefix: str, pool: Sequence[T]) -> T | None:
    """Resolve any item by ID prefix. Works on any sequence with .id attribute."""
    _, fragment = parse_ref(prefix)
    p = fragment.lower()
    matches = [item for item in pool if item.id.startswith(p)]
    return matches[0] if matches else None


def add_session(
    summary: str,
    claude_session_id: str | None = None,
    name: str | None = None,
    model: str | None = None,
) -> int:
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO sessions (summary, claude_session_id, name, model) VALUES (?, ?, ?, ?)",
            (summary, claude_session_id, name, model),
        )
        return cursor.lastrowid or 0


def update_session_summary(session_id: int, summary: str) -> None:
    with get_db() as conn:
        conn.execute("UPDATE sessions SET summary = ? WHERE id = ?", (summary, session_id))


def add_observation(body: str, tag: str | None = None, about_date: date | None = None) -> str:
    obs_id = str(_uuid.uuid4())
    with get_db() as conn:
        conn.execute(
            "INSERT INTO observations (id, body, tag, about_date) VALUES (?, ?, ?, ?)",
            (obs_id, body, tag, about_date.isoformat() if about_date else None),
        )
    return obs_id


def get_observations(limit: int = 20, tag: str | None = None) -> list[Observation]:
    with get_db() as conn:
        if tag:
            rows = conn.execute(
                "SELECT id, body, tag, logged_at, about_date "
                "FROM observations WHERE tag = ? "
                "AND deleted_at IS NULL "
                "ORDER BY logged_at DESC LIMIT ?",
                (tag, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, body, tag, logged_at, about_date "
                "FROM observations "
                "WHERE deleted_at IS NULL "
                "ORDER BY logged_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            Observation(
                id=row[0],
                body=row[1],
                tag=row[2],
                logged_at=datetime.fromisoformat(row[3]),
                about_date=date.fromisoformat(row[4]) if row[4] else None,
            )
            for row in rows
        ]


def delete_observation(prefix: str, hard: bool = False) -> bool:
    obs = resolve_prefix(prefix, get_observations(limit=200))
    if not obs:
        return False
    with get_db() as conn:
        if hard:
            cursor = conn.execute("DELETE FROM observations WHERE id = ?", (obs.id,))
        else:
            cursor = conn.execute(
                "UPDATE observations "
                "SET deleted_at = STRFTIME('%Y-%m-%dT%H:%M:%S', 'now') "
                "WHERE id = ? AND deleted_at IS NULL",
                (obs.id,),
            )
        return cursor.rowcount > 0


def get_sessions(limit: int = 10) -> list[StewardSession]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, summary, logged_at, claude_session_id, name, model "
            "FROM sessions ORDER BY logged_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            StewardSession(
                id=row[0],
                summary=row[1],
                logged_at=datetime.fromisoformat(row[2]),
                claude_session_id=row[3],
                name=row[4],
                model=row[5],
            )
            for row in rows
        ]


from . import auto, chat, close, dash, improve, log, wake  # noqa: E402

__all__ = [
    "Observation",
    "StewardSession",
    "add_observation",
    "add_session",
    "auto",
    "chat",
    "wake",
    "close",
    "dash",
    "delete_observation",
    "get_observations",
    "get_sessions",
    "improve",
    "log",
    "resolve_prefix",
    "update_session_summary",
]

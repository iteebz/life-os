import json as _json
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
    source: str | None = None
    follow_ups: list[str] | None = None


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
    source: str | None = None,
) -> int:
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO sessions (summary, claude_session_id, name, model, source) VALUES (?, ?, ?, ?, ?)",
            (summary, claude_session_id, name, model, source),
        )
        return cursor.lastrowid or 0


@dataclass(frozen=True)
class Spawn:
    id: int
    mode: str
    source: str | None
    session_id: int | None
    started_at: datetime
    ended_at: datetime | None
    runtime_seconds: int | None
    prompt_chars: int | None
    response_chars: int | None
    status: str


def add_spawn(
    mode: str,
    source: str | None = None,
    session_id: int | None = None,
    prompt_chars: int | None = None,
) -> int:
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO spawns (mode, source, session_id, prompt_chars) VALUES (?, ?, ?, ?)",
            (mode, source, session_id, prompt_chars),
        )
        return cursor.lastrowid or 0


def close_spawn(spawn_id: int, status: str = "complete", response_chars: int | None = None) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE spawns SET ended_at = STRFTIME('%Y-%m-%dT%H:%M:%S', 'now'), "
            "runtime_seconds = CAST((JULIANDAY('now') - JULIANDAY(started_at)) * 86400 AS INTEGER), "
            "status = ?, response_chars = ? "
            "WHERE id = ?",
            (status, response_chars, spawn_id),
        )


def get_spawns(mode: str | None = None, limit: int = 20) -> list[Spawn]:
    with get_db() as conn:
        if mode:
            rows = conn.execute(
                "SELECT id, mode, source, session_id, started_at, ended_at, "
                "runtime_seconds, prompt_chars, response_chars, status "
                "FROM spawns WHERE mode = ? ORDER BY started_at DESC LIMIT ?",
                (mode, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, mode, source, session_id, started_at, ended_at, "
                "runtime_seconds, prompt_chars, response_chars, status "
                "FROM spawns ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            Spawn(
                id=row[0],
                mode=row[1],
                source=row[2],
                session_id=row[3],
                started_at=datetime.fromisoformat(row[4]),
                ended_at=datetime.fromisoformat(row[5]) if row[5] else None,
                runtime_seconds=row[6],
                prompt_chars=row[7],
                response_chars=row[8],
                status=row[9],
            )
            for row in rows
        ]


def update_session_summary(session_id: int, summary: str) -> None:
    with get_db() as conn:
        conn.execute("UPDATE sessions SET summary = ? WHERE id = ?", (summary, session_id))


def update_session_followups(session_id: int, follow_ups: list[str]) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE sessions SET follow_ups = ? WHERE id = ?",
            (_json.dumps(follow_ups), session_id),
        )


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
            "SELECT id, summary, logged_at, claude_session_id, name, model, source, follow_ups "
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
                source=row[6],
                follow_ups=_json.loads(row[7]) if row[7] else None,
            )
            for row in rows
        ]


from . import auto, chat, close, dash, improve, inbox, log, wake  # noqa: E402

__all__ = [
    "Observation",
    "Spawn",
    "StewardSession",
    "add_observation",
    "add_session",
    "add_spawn",
    "auto",
    "chat",
    "close",
    "close_spawn",
    "dash",
    "delete_observation",
    "get_observations",
    "get_sessions",
    "get_spawns",
    "improve",
    "inbox",
    "log",
    "resolve_prefix",
    "update_session_followups",
    "update_session_summary",
    "wake",
]

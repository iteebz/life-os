import uuid as _uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from ..db import get_db


class _HasUUID(Protocol):
    @property
    def uuid(self) -> str: ...


@dataclass(frozen=True)
class StewardSession:
    id: int
    summary: str
    logged_at: datetime


@dataclass(frozen=True)
class Observation:
    uuid: str
    body: str
    tag: str | None
    logged_at: datetime
    about_date: date | None = None


def resolve_prefix[T: _HasUUID](prefix: str, pool: Sequence[T]) -> T | None:
    """Resolve any steward item by UUID prefix. Works on any sequence with .uuid attribute."""
    p = prefix.lower()
    matches = [item for item in pool if item.uuid.startswith(p)]
    return matches[0] if matches else None


def add_session(summary: str) -> int:
    with get_db() as conn:
        cursor = conn.execute("INSERT INTO steward_sessions (summary) VALUES (?)", (summary,))
        return cursor.lastrowid or 0


def add_observation(body: str, tag: str | None = None, about_date: date | None = None) -> str:
    obs_uuid = str(_uuid.uuid4())
    with get_db() as conn:
        conn.execute(
            "INSERT INTO observations (uuid, body, tag, about_date) VALUES (?, ?, ?, ?)",
            (obs_uuid, body, tag, about_date.isoformat() if about_date else None),
        )
    return obs_uuid


def get_observations(limit: int = 20, tag: str | None = None) -> list[Observation]:
    with get_db() as conn:
        if tag:
            rows = conn.execute(
                "SELECT uuid, body, tag, logged_at, about_date FROM observations WHERE tag = ? AND deleted_at IS NULL ORDER BY logged_at DESC LIMIT ?",
                (tag, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT uuid, body, tag, logged_at, about_date FROM observations WHERE deleted_at IS NULL ORDER BY logged_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            Observation(
                uuid=row[0],
                body=row[1],
                tag=row[2],
                logged_at=datetime.fromisoformat(row[3]),
                about_date=date.fromisoformat(row[4]) if row[4] else None,
            )
            for row in rows
        ]


def delete_observation(prefix: str) -> bool:
    obs = resolve_prefix(prefix, get_observations(limit=200))
    if not obs:
        return False
    with get_db() as conn:
        cursor = conn.execute(
            "UPDATE observations SET deleted_at = STRFTIME('%Y-%m-%dT%H:%M:%S', 'now') WHERE uuid = ? AND deleted_at IS NULL",
            (obs.uuid,),
        )
        return cursor.rowcount > 0


def get_sessions(limit: int = 10) -> list[StewardSession]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, summary, logged_at FROM steward_sessions ORDER BY logged_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            StewardSession(id=row[0], summary=row[1], logged_at=datetime.fromisoformat(row[2]))
            for row in rows
        ]


def _rel(secs: float) -> str:
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    return f"{int(secs // 86400)}d ago"


from . import auto, boot, close, dash, improve, log  # noqa: E402

__all__ = [
    "Observation",
    "StewardSession",
    "_rel",
    "add_observation",
    "add_session",
    "auto",
    "boot",
    "close",
    "dash",
    "delete_observation",
    "get_observations",
    "get_sessions",
    "improve",
    "log",
    "resolve_prefix",
]

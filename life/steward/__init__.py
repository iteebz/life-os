from dataclasses import dataclass
from datetime import date, datetime

from ..db import get_db


@dataclass(frozen=True)
class StewardSession:
    id: int
    summary: str
    logged_at: datetime


@dataclass(frozen=True)
class Observation:
    id: int
    body: str
    tag: str | None
    logged_at: datetime
    about_date: date | None = None


def add_session(summary: str) -> int:
    with get_db() as conn:
        cursor = conn.execute("INSERT INTO steward_sessions (summary) VALUES (?)", (summary,))
        return cursor.lastrowid or 0


def add_observation(body: str, tag: str | None = None, about_date: date | None = None) -> int:
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO observations (body, tag, about_date) VALUES (?, ?, ?)",
            (body, tag, about_date.isoformat() if about_date else None),
        )
        return cursor.lastrowid or 0


def get_observations(limit: int = 20, tag: str | None = None) -> list[Observation]:
    with get_db() as conn:
        if tag:
            rows = conn.execute(
                "SELECT id, body, tag, logged_at, about_date FROM observations WHERE tag = ? ORDER BY logged_at DESC LIMIT ?",
                (tag, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, body, tag, logged_at, about_date FROM observations ORDER BY logged_at DESC LIMIT ?",
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


def delete_observation(obs_id: int) -> bool:
    with get_db() as conn:
        cursor = conn.execute("DELETE FROM observations WHERE id = ?", (obs_id,))
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
]

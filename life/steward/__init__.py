import json
import os
import uuid
from dataclasses import dataclass
from datetime import date, datetime

from life.lib.ids import resolve_prefix
from life.lib.store import get_db


@dataclass(frozen=True)
class Session:
    id: int
    summary: str
    logged_at: datetime
    provider_session_id: str | None = None
    name: str | None = None
    model: str | None = None
    source: str | None = None
    follow_ups: list[str] | None = None
    state: str = "closed"
    started_at: datetime | None = None
    last_active_at: datetime | None = None
    ended_at: datetime | None = None
    pid: int | None = None
    welfare: int | None = None


@dataclass(frozen=True)
class Observation:
    id: str
    body: str
    tag: str | None
    logged_at: datetime
    about_date: date | None = None


# --- Session CRUD ---


def create_session(
    summary: str,
    provider_session_id: str | None = None,
    name: str | None = None,
    model: str | None = None,
    source: str | None = None,
    pid: int | None = None,
    chat_id: str | None = None,
) -> int:
    with get_db() as conn:
        conn.execute(
            "UPDATE sessions SET state = 'closed', "
            "ended_at = STRFTIME('%Y-%m-%dT%H:%M:%S', 'now', 'localtime') "
            "WHERE state IN ('active', 'idle')"
        )
        cursor = conn.execute(
            "INSERT INTO sessions (summary, provider_session_id, name, model, source, "
            "state, started_at, last_active_at, pid, chat_id) "
            "VALUES (?, ?, ?, ?, ?, 'active', STRFTIME('%Y-%m-%dT%H:%M:%S', 'now', 'localtime'), "
            "STRFTIME('%Y-%m-%dT%H:%M:%S', 'now', 'localtime'), ?, ?)",
            (summary, provider_session_id, name, model, source, pid, chat_id),
        )
        return cursor.lastrowid or 0


def touch_session(session_id: int) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE sessions SET last_active_at = STRFTIME('%Y-%m-%dT%H:%M:%S', 'now', 'localtime') WHERE id = ?",
            (session_id,),
        )


def set_session_pid(session_id: int, pid: int) -> None:
    with get_db() as conn:
        conn.execute("UPDATE sessions SET pid = ? WHERE id = ?", (pid, session_id))


def set_session_active(session_id: int) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE sessions SET state = 'active', "
            "last_active_at = STRFTIME('%Y-%m-%dT%H:%M:%S', 'now', 'localtime') WHERE id = ?",
            (session_id,),
        )


def set_session_idle(session_id: int) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE sessions SET state = 'idle', "
            "last_active_at = STRFTIME('%Y-%m-%dT%H:%M:%S', 'now', 'localtime') WHERE id = ?",
            (session_id,),
        )


def close_session(
    session_id: int,
    summary: str | None = None,
    welfare: int | None = None,
) -> None:
    sets = [
        "state = 'closed'",
        "ended_at = STRFTIME('%Y-%m-%dT%H:%M:%S', 'now', 'localtime')",
        "last_active_at = STRFTIME('%Y-%m-%dT%H:%M:%S', 'now', 'localtime')",
        "runtime_seconds = CAST((JULIANDAY('now') - JULIANDAY(started_at)) * 86400 AS INTEGER)",
        "pid = NULL",
    ]
    params: list[object] = []
    if summary:
        sets.append("summary = ?")
        params.append(summary)
    if welfare is not None:
        sets.append("welfare = ?")
        params.append(welfare)
    params.append(session_id)
    with get_db() as conn:
        conn.execute(f"UPDATE sessions SET {', '.join(sets)} WHERE id = ?", params)


TG_WARM_WINDOW_SECONDS = 55 * 60  # 55m — stays within 1hr cache window


def current_session(chat_id: str | None = None) -> Session | None:
    """Most recently active resumable session within the warm window.

    If chat_id is given, scopes to that TG conversation's session.
    """
    if chat_id is not None:
        with get_db() as conn:
            row = conn.execute(
                "SELECT id, summary, logged_at, provider_session_id, name, model, source, "
                "follow_ups, state, started_at, last_active_at, ended_at, pid, welfare "
                "FROM sessions "
                "WHERE state IN ('active', 'idle') AND chat_id = ? "
                "AND last_active_at >= STRFTIME('%Y-%m-%dT%H:%M:%S', 'now', 'localtime', ?)"
                "ORDER BY last_active_at DESC LIMIT 1",
                (chat_id, f"-{TG_WARM_WINDOW_SECONDS} seconds"),
            ).fetchone()
    else:
        with get_db() as conn:
            row = conn.execute(
                "SELECT id, summary, logged_at, provider_session_id, name, model, source, "
                "follow_ups, state, started_at, last_active_at, ended_at, pid, welfare "
                "FROM sessions "
                "WHERE state IN ('active', 'idle') "
                "ORDER BY last_active_at DESC LIMIT 1"
            ).fetchone()
    if not row:
        return None
    return _row_to_session(row)


def hookable_session() -> Session | None:
    """Find an interactive session with a live process (pid alive = cli window open)."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, summary, logged_at, provider_session_id, name, model, source, "
            "follow_ups, state, started_at, last_active_at, ended_at, pid, welfare "
            "FROM sessions "
            "WHERE state IN ('active', 'idle') AND pid IS NOT NULL "
            "ORDER BY last_active_at DESC"
        ).fetchall()
    for row in rows:
        pid = row[12]
        if pid and _pid_alive(pid):
            return _row_to_session(row)
    return None


def messages_since_last_auto_session() -> int:
    """Return count of inbound human messages (any session) since the last auto session started."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT started_at FROM sessions WHERE source = 'auto' "
            "ORDER BY COALESCE(started_at, logged_at) DESC LIMIT 1"
        ).fetchone()
        if not row or not row[0]:
            return 0
        started_at = row[0]
        count = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE direction = 'in' AND logged_at > ?",
            (started_at,),
        ).fetchone()
    return count[0] if count else 0


def get_sessions(limit: int = 10, state: str | None = None) -> list[Session]:
    with get_db() as conn:
        if state:
            rows = conn.execute(
                "SELECT id, summary, logged_at, provider_session_id, name, model, source, "
                "follow_ups, state, started_at, last_active_at, ended_at, pid, welfare "
                "FROM sessions WHERE state = ? ORDER BY COALESCE(last_active_at, logged_at) DESC LIMIT ?",
                (state, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, summary, logged_at, provider_session_id, name, model, source, "
                "follow_ups, state, started_at, last_active_at, ended_at, pid, welfare "
                "FROM sessions ORDER BY COALESCE(last_active_at, logged_at) DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [_row_to_session(row) for row in rows]


def update_session_claude_id(session_id: int, provider_session_id: str) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE sessions SET provider_session_id = ? WHERE id = ?",
            (provider_session_id, session_id),
        )


def update_session_summary(session_id: int, summary: str) -> None:
    with get_db() as conn:
        conn.execute("UPDATE sessions SET summary = ? WHERE id = ?", (summary, session_id))


def update_session_followups(session_id: int, follow_ups: list[str]) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE sessions SET follow_ups = ? WHERE id = ?",
            (json.dumps(follow_ups), session_id),
        )


def _row_to_session(row: tuple) -> Session:  # type: ignore[type-arg]
    return Session(
        id=row[0],
        summary=row[1],
        logged_at=datetime.fromisoformat(row[2]),
        provider_session_id=row[3],
        name=row[4],
        model=row[5],
        source=row[6],
        follow_ups=json.loads(row[7]) if row[7] else None,
        state=row[8],
        started_at=datetime.fromisoformat(row[9]) if row[9] else None,
        last_active_at=datetime.fromisoformat(row[10]) if row[10] else None,
        ended_at=datetime.fromisoformat(row[11]) if row[11] else None,
        pid=row[12],
        welfare=row[13] if len(row) > 13 else None,
    )


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


# --- Observations ---


def add_observation(body: str, tag: str | None = None, about_date: date | None = None) -> str:
    obs_id = str(uuid.uuid4())
    with get_db() as conn:
        conn.execute(
            "INSERT INTO observations (id, body, tag, about_date) VALUES (?, ?, ?, ?)",
            (obs_id, body, tag, about_date.isoformat() if about_date else None),
        )
    return obs_id


def get_observations(limit: int = 20, tag: str | None = None, search: str | None = None) -> list[Observation]:
    with get_db() as conn:
        conditions = ["deleted_at IS NULL"]
        params: list[str | int] = []
        if tag:
            conditions.append("tag = ?")
            params.append(tag)
        if search:
            conditions.append("body LIKE ?")
            params.append(f"%{search}%")
        where = " AND ".join(conditions)
        params.append(limit)
        query = (
            "SELECT id, body, tag, logged_at, about_date FROM observations WHERE "
            + where
            + " ORDER BY logged_at DESC LIMIT ?"
        )
        rows = conn.execute(query, params).fetchall()
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
                "SET deleted_at = STRFTIME('%Y-%m-%dT%H:%M:%S', 'now', 'localtime') "
                "WHERE id = ? AND deleted_at IS NULL",
                (obs.id,),
            )
        return cursor.rowcount > 0


add_session = create_session


from . import auto, chat, ctx, dash, improve, inbox, log, notes, recall, sleep, trails, wake

__all__ = [
    "Observation",
    "Session",
    "add_observation",
    "add_session",
    "auto",
    "chat",
    "close_session",
    "create_session",
    "ctx",
    "current_session",
    "dash",
    "delete_observation",
    "get_observations",
    "get_sessions",
    "hookable_session",
    "improve",
    "inbox",
    "log",
    "notes",
    "recall",
    "resolve_prefix",
    "set_session_active",
    "set_session_idle",
    "set_session_pid",
    "sleep",
    "touch_session",
    "trails",
    "update_session_claude_id",
    "update_session_followups",
    "update_session_summary",
    "wake",
]

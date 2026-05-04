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
    claude_session_id: str | None = None
    name: str | None = None
    model: str | None = None
    source: str | None = None
    follow_ups: list[str] | None = None
    state: str = "closed"
    started_at: datetime | None = None
    last_active_at: datetime | None = None
    ended_at: datetime | None = None
    pid: int | None = None
    handover: str | None = None
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
    claude_session_id: str | None = None,
    name: str | None = None,
    model: str | None = None,
    source: str | None = None,
    pid: int | None = None,
) -> int:
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO sessions (summary, claude_session_id, name, model, source, "
            "state, started_at, last_active_at, pid) "
            "VALUES (?, ?, ?, ?, ?, 'active', STRFTIME('%Y-%m-%dT%H:%M:%S', 'now', 'localtime'), "
            "STRFTIME('%Y-%m-%dT%H:%M:%S', 'now', 'localtime'), ?)",
            (summary, claude_session_id, name, model, source, pid),
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
    handover: str | None = None,
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
    if handover is not None:
        sets.append("handover = ?")
        params.append(handover or None)
    if welfare is not None:
        sets.append("welfare = ?")
        params.append(welfare)
    params.append(session_id)
    with get_db() as conn:
        conn.execute(f"UPDATE sessions SET {', '.join(sets)} WHERE id = ?", params)  # noqa: S608


def latest_handover() -> str | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT handover FROM sessions WHERE handover IS NOT NULL "
            "ORDER BY COALESCE(ended_at, last_active_at, logged_at) DESC LIMIT 1"
        ).fetchone()
    return row[0] if row else None


def update_session_handover(text: str) -> int:
    """Set handover on the most recent session (active, idle, or closed). Returns affected count."""
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE sessions SET handover = ? WHERE id = ("
            "SELECT id FROM sessions ORDER BY COALESCE(last_active_at, logged_at) DESC LIMIT 1)",
            (text,),
        )
        return cur.rowcount


def clear_handover() -> int:
    """Null the handover on the most recent session that has one. Returns affected count."""
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE sessions SET handover = NULL WHERE id = ("
            "SELECT id FROM sessions WHERE handover IS NOT NULL "
            "ORDER BY COALESCE(ended_at, last_active_at, logged_at) DESC LIMIT 1)"
        )
        return cur.rowcount


def current_session() -> Session | None:
    """Most recently active resumable session (active or idle within warm window)."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, summary, logged_at, claude_session_id, name, model, source, "
            "follow_ups, state, started_at, last_active_at, ended_at, pid, handover, welfare "
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
            "SELECT id, summary, logged_at, claude_session_id, name, model, source, "
            "follow_ups, state, started_at, last_active_at, ended_at, pid, handover, welfare "
            "FROM sessions "
            "WHERE state IN ('active', 'idle') AND pid IS NOT NULL "
            "ORDER BY last_active_at DESC"
        ).fetchall()
    for row in rows:
        pid = row[12]
        if pid and _pid_alive(pid):
            return _row_to_session(row)
    return None


def get_sessions(limit: int = 10, state: str | None = None) -> list[Session]:
    with get_db() as conn:
        if state:
            rows = conn.execute(
                "SELECT id, summary, logged_at, claude_session_id, name, model, source, "
                "follow_ups, state, started_at, last_active_at, ended_at, pid, handover, welfare "
                "FROM sessions WHERE state = ? ORDER BY COALESCE(last_active_at, logged_at) DESC LIMIT ?",
                (state, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, summary, logged_at, claude_session_id, name, model, source, "
                "follow_ups, state, started_at, last_active_at, ended_at, pid, handover, welfare "
                "FROM sessions ORDER BY COALESCE(last_active_at, logged_at) DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [_row_to_session(row) for row in rows]


def update_session_claude_id(session_id: int, claude_session_id: str) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE sessions SET claude_session_id = ? WHERE id = ?",
            (claude_session_id, session_id),
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
        claude_session_id=row[3],
        name=row[4],
        model=row[5],
        source=row[6],
        follow_ups=json.loads(row[7]) if row[7] else None,
        state=row[8],
        started_at=datetime.fromisoformat(row[9]) if row[9] else None,
        last_active_at=datetime.fromisoformat(row[10]) if row[10] else None,
        ended_at=datetime.fromisoformat(row[11]) if row[11] else None,
        pid=row[12],
        handover=row[13] if len(row) > 13 else None,
        welfare=row[14] if len(row) > 14 else None,
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
                "SET deleted_at = STRFTIME('%Y-%m-%dT%H:%M:%S', 'now', 'localtime') "
                "WHERE id = ? AND deleted_at IS NULL",
                (obs.id,),
            )
        return cursor.rowcount > 0


add_session = create_session


from . import auto, chat, dash, improve, inbox, log, sleep, wake  # noqa: E402

__all__ = [
    "Observation",
    "Session",
    "add_observation",
    "add_session",
    "auto",
    "chat",
    "close_session",
    "create_session",
    "current_session",
    "dash",
    "delete_observation",
    "get_observations",
    "get_sessions",
    "hookable_session",
    "improve",
    "inbox",
    "log",
    "resolve_prefix",
    "set_session_active",
    "set_session_idle",
    "set_session_pid",
    "sleep",
    "touch_session",
    "update_session_claude_id",
    "update_session_followups",
    "update_session_summary",
    "wake",
]

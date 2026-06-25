"""steward ping — broadcast a message to all live (active) steward sessions."""

import os
from datetime import UTC, datetime

from fncli import cli

from life.lib.store import get_db


def send(message: str) -> int:
    """Write a ping row. Returns the new ping id."""
    session_id = os.environ.get("STEWARD_DB_SESSION_ID") or os.environ.get("STEWARD_SESSION_ID")
    from_id: int | None = None
    if session_id and session_id.isdigit():
        from_id = int(session_id)
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO pings (message, from_session_id) VALUES (?, ?)",
            (message, from_id),
        )
        return cur.lastrowid or 0


def drain(last_ping_id: int) -> tuple[list[tuple[int, str]], int]:
    """Return pings created after last_ping_id (excluding own session). Updates watermark."""
    session_id = os.environ.get("STEWARD_DB_SESSION_ID") or os.environ.get("STEWARD_SESSION_ID")
    from_id: int | None = None
    if session_id and session_id.isdigit():
        from_id = int(session_id)
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, message FROM pings WHERE id > ? AND (from_session_id IS NULL OR from_session_id != ?) ORDER BY id ASC",
            (last_ping_id, from_id or -1),
        ).fetchall()
        max_id = conn.execute("SELECT COALESCE(MAX(id), 0) FROM pings").fetchone()[0]
    return [(r[0], r[1]) for r in rows], max_id


@cli("life steward")
def ping(message: str) -> None:
    """Broadcast a message to all live steward sessions."""
    ping_id = send(message)
    now = datetime.now(UTC).strftime("%H:%M:%S")
    print(f"ping #{ping_id} sent at {now}: {message}")

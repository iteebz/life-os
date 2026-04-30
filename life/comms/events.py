"""Event log. Single write path for all message events.

Every inbound, outbound, ack, resume, spawn, drop, error gets a row.
Channel-specific shape lives in payload (json).
"""

import contextlib
import json
import time
from collections.abc import Mapping

from life.comms.peers import resolve_or_create
from life.lib.store import get_db

_INBOX_LIMIT = 10


def _select_unsurfaced(conn, limit: int = _INBOX_LIMIT):
    return conn.execute(
        "SELECT e.id, e.channel, p.display_name, json_extract(e.payload, '$.body'), e.ts "
        "FROM events e LEFT JOIN peers p ON p.id = e.peer_id "
        "WHERE e.kind = 'inbound' "
        "AND json_extract(e.payload, '$.surfaced_at') IS NULL "
        "ORDER BY e.ts ASC LIMIT ?",
        (limit,),
    ).fetchall()


def peek_inbox() -> list[tuple[int, str, str, str, int]]:
    """Unsurfaced inbound events (id, channel, peer_name, body, ts). No mutation."""
    with get_db() as conn:
        return _select_unsurfaced(conn)


def drain_inbox() -> list[tuple[int, str, str, str, int]]:
    """Like peek_inbox, but marks each event surfaced. Exactly-once."""
    with get_db() as conn:
        rows = _select_unsurfaced(conn)
        if not rows:
            return []
        ids = [r[0] for r in rows]
        placeholders = ",".join("?" for _ in ids)
        conn.execute(
            f"UPDATE events SET payload = json_set(payload, '$.surfaced_at', strftime('%s','now')) "  # noqa: S608
            f"WHERE id IN ({placeholders})",
            ids,
        )
    return rows


def mark_read_for_session(chat_id: int) -> None:
    with contextlib.suppress(Exception), get_db() as conn:
        conn.execute(
            "UPDATE events SET payload = json_set(payload, '$.read_at', datetime('now')) "
            "WHERE kind = 'inbound' AND channel = 'telegram' "
            "AND json_extract(payload, '$.read_at') IS NULL "
            "AND peer_id IN ("
            "  SELECT pa.peer_id FROM peer_addresses pa "
            "  WHERE pa.channel = 'telegram' AND pa.address = ?"
            ")",
            (str(chat_id),),
        )

_DIRECTION_TO_KIND = {"in": "inbound", "out": "outbound"}


def record_message(
    channel: str,
    address: str,
    direction: str,
    body: str,
    timestamp: int,
    *,
    raw_id: str | None = None,
    peer_name: str | None = None,
    subject: str | None = None,
    image_path: str | None = None,
    group_id: str | None = None,
    success: int | None = None,
    error: str | None = None,
    sent_by: str = "steward",
) -> int:
    """Record an inbound or outbound message. Returns event id.

    Idempotent on raw_id: if raw_id already exists in payload, no-op.
    """
    if raw_id:
        with get_db() as conn:
            row = conn.execute(
                "SELECT id FROM events "
                "WHERE channel = ? AND json_extract(payload, '$.raw_id') = ?",
                (channel, raw_id),
            ).fetchone()
            if row:
                return row[0]

    peer_id = resolve_or_create(channel, address, peer_name)
    kind = _DIRECTION_TO_KIND.get(direction, direction)
    payload = json.dumps(
        {
            "body": body,
            "raw_id": raw_id,
            "subject": subject,
            "image_path": image_path,
            "group_id": group_id,
            "success": success,
            "error": error,
            "sent_by": sent_by,
        }
    )
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO events (ts, kind, peer_id, channel, payload) "
            "VALUES (?, ?, ?, ?, ?)",
            (timestamp, kind, peer_id, channel, payload),
        )
        return cursor.lastrowid


def record(
    kind: str,
    *,
    peer_id: int | None = None,
    channel: str | None = None,
    ref_id: int | None = None,
    session_id: int | None = None,
    payload: Mapping[str, object] | None = None,
    timestamp: int | None = None,
) -> int:
    """Record a non-message event (ack, resume, spawn, drop, error). Returns id."""
    ts = timestamp if timestamp is not None else int(time.time())
    body = json.dumps(payload or {})
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO events (ts, kind, peer_id, channel, ref_id, session_id, payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ts, kind, peer_id, channel, ref_id, session_id, body),
        )
        return cursor.lastrowid

"""Event log. Single write path for all message events.

Every inbound, outbound, ack, resume, spawn, drop, error gets a row.
Channel-specific shape lives in payload (json).
"""

import json
import time
from collections.abc import Mapping

from life.comms.peers import resolve_or_create
from life.lib.store import get_db

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

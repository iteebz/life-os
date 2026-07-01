"""Utterance corpus. Tyson's raw messages, indexed for recall and ICL."""

import json

from lifeos.core.lib.store import get_db


def _extract_body(payload: str) -> str | None:
    try:
        return json.loads(payload).get("body")
    except Exception:
        return None


def backfill() -> int:
    """Extract all inbound events not yet in utterances. Returns count inserted."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT e.id, e.session_id, json_extract(e.payload, '$.body'), e.ts "
            "FROM events e "
            "WHERE e.kind = 'inbound' "
            "AND e.id NOT IN (SELECT event_id FROM utterances WHERE event_id IS NOT NULL)",
        ).fetchall()
        count = 0
        for event_id, session_id, body, ts in rows:
            if not body or not body.strip():
                continue
            conn.execute(
                "INSERT OR IGNORE INTO utterances (event_id, session_id, body, ts, source) "
                "VALUES (?, ?, ?, ?, 'human')",
                (event_id, session_id, body, ts),
            )
            count += 1
        conn.commit()
        return count


def record(body: str, event_id: int | None = None, session_id: int | None = None, ts: int | None = None) -> int:
    """Insert a single human utterance. Returns new row id."""
    if ts is None:
        import time

        ts = int(time.time())
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO utterances (event_id, session_id, body, ts, source) VALUES (?, ?, ?, ?, 'human')",
            (event_id, session_id, body, ts),
        )
        conn.commit()
        return cur.lastrowid  # type: ignore[return-value]


def search(query: str, limit: int = 10) -> list[dict]:
    """FTS search over utterances. Returns list of {id, body, ts, session_id}."""
    with get_db() as conn:
        # quote each term so FTS5 special chars (', -, ", etc.) in raw speech don't break MATCH syntax
        fts_query = " ".join(f'"{w}"' for w in query.split() if w)
        rows = conn.execute(
            "SELECT u.id, u.body, u.ts, u.session_id "
            "FROM utterances_fts f "
            "JOIN utterances u ON u.id = f.rowid "
            "WHERE utterances_fts MATCH ? "
            "ORDER BY rank LIMIT ?",
            (fts_query, limit),
        ).fetchall()
        return [{"id": r[0], "body": r[1], "ts": r[2], "session_id": r[3]} for r in rows]


def count() -> int:
    with get_db() as conn:
        return conn.execute("SELECT COUNT(*) FROM utterances").fetchone()[0]

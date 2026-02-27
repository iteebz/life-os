import uuid as _uuid
from dataclasses import dataclass
from datetime import datetime

from .db import get_db


@dataclass(frozen=True)
class Improvement:
    uuid: str
    body: str
    logged_at: datetime
    done_at: datetime | None = None


def add_improvement(body: str) -> str:
    imp_uuid = str(_uuid.uuid4())
    with get_db() as conn:
        conn.execute("INSERT INTO improvements (uuid, body) VALUES (?, ?)", (imp_uuid, body))
    return imp_uuid


def get_improvements(done: bool = False) -> list[Improvement]:
    with get_db() as conn:
        if done:
            rows = conn.execute(
                "SELECT uuid, body, logged_at, done_at FROM improvements WHERE deleted_at IS NULL ORDER BY logged_at DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT uuid, body, logged_at, done_at FROM improvements WHERE done_at IS NULL AND deleted_at IS NULL ORDER BY logged_at DESC"
            ).fetchall()
        return [
            Improvement(
                uuid=row[0],
                body=row[1],
                logged_at=datetime.fromisoformat(row[2]),
                done_at=datetime.fromisoformat(row[3]) if row[3] else None,
            )
            for row in rows
        ]


def delete_improvement(prefix: str, hard: bool = False) -> bool:
    from .steward import resolve_prefix

    imp = resolve_prefix(prefix, get_improvements())
    if not imp:
        return False
    with get_db() as conn:
        if hard:
            cursor = conn.execute("DELETE FROM improvements WHERE uuid = ?", (imp.uuid,))
        else:
            cursor = conn.execute(
                "UPDATE improvements SET deleted_at = STRFTIME('%Y-%m-%dT%H:%M:%S', 'now') WHERE uuid = ? AND deleted_at IS NULL",
                (imp.uuid,),
            )
        return cursor.rowcount > 0


def mark_improvement_done(query: str) -> Improvement | None:
    from .steward import resolve_prefix

    improvements = get_improvements()
    # try UUID prefix first, fall back to substring
    imp = resolve_prefix(query, improvements)
    if not imp:
        q = query.lower()
        matches = [i for i in improvements if q in i.body.lower()]
        imp = matches[0] if matches else None
    if not imp:
        return None
    with get_db() as conn:
        conn.execute(
            "UPDATE improvements SET done_at = STRFTIME('%Y-%m-%dT%H:%M:%S', 'now') WHERE uuid = ?",
            (imp.uuid,),
        )
    return imp

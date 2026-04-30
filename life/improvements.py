import uuid
from dataclasses import dataclass
from datetime import datetime

from life.lib.ids import resolve_prefix
from life.lib.store import get_db


@dataclass(frozen=True)
class Improvement:
    id: str
    body: str
    logged_at: datetime
    done_at: datetime | None = None


def add_improvement(body: str) -> str:
    imp_id = str(uuid.uuid4())
    with get_db() as conn:
        conn.execute("INSERT INTO improvements (id, body) VALUES (?, ?)", (imp_id, body))
    return imp_id


def get_improvements(done: bool = False) -> list[Improvement]:
    with get_db() as conn:
        if done:
            rows = conn.execute(
                "SELECT id, body, logged_at, done_at FROM improvements WHERE deleted_at IS NULL ORDER BY logged_at DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, body, logged_at, done_at FROM improvements "
                "WHERE done_at IS NULL AND deleted_at IS NULL "
                "ORDER BY logged_at DESC"
            ).fetchall()
        return [
            Improvement(
                id=row[0],
                body=row[1],
                logged_at=datetime.fromisoformat(row[2]),
                done_at=datetime.fromisoformat(row[3]) if row[3] else None,
            )
            for row in rows
        ]


def delete_improvement(prefix: str, hard: bool = False) -> bool:
    imp = resolve_prefix(prefix, get_improvements())
    if not imp:
        return False
    with get_db() as conn:
        if hard:
            cursor = conn.execute("DELETE FROM improvements WHERE id = ?", (imp.id,))
        else:
            cursor = conn.execute(
                "UPDATE improvements "
                "SET deleted_at = STRFTIME('%Y-%m-%dT%H:%M:%S', 'now') "
                "WHERE id = ? AND deleted_at IS NULL",
                (imp.id,),
            )
        return cursor.rowcount > 0


def mark_improvement_done(query: str) -> Improvement | None:
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
            "UPDATE improvements SET done_at = STRFTIME('%Y-%m-%dT%H:%M:%S', 'now') WHERE id = ?",
            (imp.id,),
        )
    return imp

from dataclasses import dataclass
from datetime import datetime

from .db import get_db


@dataclass(frozen=True)
class Improvement:
    id: int
    body: str
    logged_at: datetime
    done_at: datetime | None = None


def add_improvement(body: str) -> int:
    with get_db() as conn:
        cursor = conn.execute("INSERT INTO improvements (body) VALUES (?)", (body,))
        return cursor.lastrowid or 0


def get_improvements(done: bool = False) -> list[Improvement]:
    with get_db() as conn:
        if done:
            rows = conn.execute(
                "SELECT id, body, logged_at, done_at FROM improvements WHERE deleted_at IS NULL ORDER BY logged_at DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, body, logged_at, done_at FROM improvements WHERE done_at IS NULL AND deleted_at IS NULL ORDER BY logged_at DESC"
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


def delete_improvement(imp_id: int) -> bool:
    with get_db() as conn:
        cursor = conn.execute(
            "UPDATE improvements SET deleted_at = STRFTIME('%Y-%m-%dT%H:%M:%S', 'now') WHERE id = ? AND deleted_at IS NULL",
            (imp_id,),
        )
        return cursor.rowcount > 0


def mark_improvement_done(query: str) -> Improvement | None:
    improvements = get_improvements()
    if not improvements:
        return None
    # try ID first
    try:
        imp_id = int(query)
        matches = [i for i in improvements if i.id == imp_id]
    except ValueError:
        q = query.lower()
        matches = [i for i in improvements if q in i.body.lower()]
    if not matches:
        return None
    target = matches[0]
    with get_db() as conn:
        conn.execute(
            "UPDATE improvements SET done_at = STRFTIME('%Y-%m-%dT%H:%M:%S', 'now') WHERE id = ?",
            (target.id,),
        )
    return target

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from lifeos.core.lib.ids import resolve_prefix
from lifeos.core.lib.store import get_db


@dataclass(frozen=True)
class Improvement:
    id: str
    body: str
    logged_at: datetime
    done_at: datetime | None = None
    promoted_at: datetime | None = None
    trail: str | None = None


def add_improvement(body: str) -> str:
    imp_id = str(uuid.uuid4())
    with get_db() as conn:
        conn.execute("INSERT INTO improvements (id, body) VALUES (?, ?)", (imp_id, body))
    return imp_id


def _row_to_improvement(row: tuple[str, str, str, str | None, str | None, str | None]) -> Improvement:
    return Improvement(
        id=row[0],
        body=row[1],
        logged_at=datetime.fromisoformat(row[2]),
        done_at=datetime.fromisoformat(row[3]) if row[3] else None,
        promoted_at=datetime.fromisoformat(row[4]) if row[4] else None,
        trail=row[5],
    )


def get_improvements(done: bool = False, include_promoted: bool = False) -> list[Improvement]:
    with get_db() as conn:
        if done:
            rows = conn.execute(
                "SELECT id, body, logged_at, done_at, promoted_at, trail "
                "FROM improvements WHERE deleted_at IS NULL ORDER BY logged_at DESC"
            ).fetchall()
        elif include_promoted:
            rows = conn.execute(
                "SELECT id, body, logged_at, done_at, promoted_at, trail "
                "FROM improvements WHERE done_at IS NULL AND deleted_at IS NULL "
                "ORDER BY logged_at DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, body, logged_at, done_at, promoted_at, trail "
                "FROM improvements WHERE done_at IS NULL AND promoted_at IS NULL AND deleted_at IS NULL "
                "ORDER BY logged_at DESC"
            ).fetchall()
        return [_row_to_improvement(row) for row in rows]


def get_improvements_done_on(on_date: date) -> list[Improvement]:
    """Improvements closed on a given day — the daily shipped ledger."""
    day = on_date.isoformat()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, body, logged_at, done_at, promoted_at, trail "
            "FROM improvements WHERE deleted_at IS NULL AND done_at IS NOT NULL "
            "AND DATE(done_at) = ? ORDER BY done_at DESC",
            (day,),
        ).fetchall()
        return [_row_to_improvement(row) for row in rows]


def promote_improvement(query: str, trail: str) -> Improvement | None:
    improvements = get_improvements(include_promoted=True)
    imp = resolve_prefix(query, improvements)
    if not imp:
        q = query.lower()
        matches = [i for i in improvements if q in i.body.lower()]
        imp = matches[0] if matches else None
    if not imp:
        return None
    with get_db() as conn:
        conn.execute(
            "UPDATE improvements SET promoted_at = STRFTIME('%Y-%m-%dT%H:%M:%S', 'now'), trail = ? WHERE id = ?",
            (trail, imp.id),
        )
    return imp


def delete_improvement(prefix: str, hard: bool = False) -> bool:
    imp = resolve_prefix(prefix, get_improvements(include_promoted=True))
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
    improvements = get_improvements(include_promoted=True)
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

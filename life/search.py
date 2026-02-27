from dataclasses import dataclass

from . import db
from .habit import get_habits
from .lib.converters import row_to_task
from .lib.fuzzy import find_in_pool
from .task import get_tasks


@dataclass(frozen=True)
class SearchResult:
    id: str
    content: str
    type: str
    rank: float
    task: object = None
    tag: str | None = None


def search_tasks(query: str, limit: int = 20) -> list[SearchResult]:
    if not query or not query.strip():
        return []

    with db.get_db() as conn:
        rows = conn.execute(
            """
            SELECT t.id, t.content, t.focus, t.scheduled_date, t.created, t.completed_at,
                   t.parent_id, t.scheduled_time, t.blocked_by, t.description,
                   t.steward, t.source, t.is_deadline,
                   fts.rank
            FROM tasks_fts fts
            JOIN tasks t ON fts.rowid = t.rowid
            WHERE fts.content MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, limit),
        ).fetchall()

        results = []
        for row in rows:
            task = row_to_task(row)
            results.append(
                SearchResult(id=task.id, content=task.content, type="task", rank=row[-1], task=task)
            )
        return results


def search_habits(query: str, limit: int = 20) -> list[SearchResult]:
    if not query or not query.strip():
        return []

    with db.get_db() as conn:
        rows = conn.execute(
            """
            SELECT h.id, h.content, h.created,
                   fts.rank
            FROM habits_fts fts
            JOIN habits h ON fts.rowid = h.rowid
            WHERE fts.content MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, limit),
        ).fetchall()

        return [SearchResult(id=row[0], content=row[1], type="habit", rank=row[3]) for row in rows]


def search_tags(query: str, limit: int = 20) -> list[SearchResult]:
    if not query or not query.strip():
        return []

    with db.get_db() as conn:
        rows = conn.execute(
            """
            SELECT t.tag, t.task_id, t.habit_id,
                   fts.rank
            FROM tags_fts fts
            JOIN tags t ON fts.rowid = t.rowid
            WHERE fts.tag MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, limit),
        ).fetchall()

        results = []
        for row in rows:
            tag_name, task_id, habit_id, rank = row
            results.append(
                SearchResult(id=task_id or habit_id or "", content=tag_name, type="tag", rank=rank)
            )
        return results


def search_by_tag(tag: str, limit: int = 20) -> list[SearchResult]:
    """Search for tasks and habits by exact tag match."""
    if not tag or not tag.strip():
        return []

    tag = tag.strip().lstrip("#")

    with db.get_db() as conn:
        rows = conn.execute(
            """
            SELECT t.id, t.content, t.focus, t.scheduled_date, t.created, t.completed_at,
                   t.parent_id, t.scheduled_time, t.blocked_by, t.description,
                   t.steward, t.source, t.is_deadline,
                   0.0 as rank
            FROM tasks t
            JOIN tags tg ON t.id = tg.task_id
            WHERE tg.tag = ? COLLATE NOCASE
            """,
            (tag,),
        ).fetchall()

        results = []
        for row in rows:
            task = row_to_task(row)
            results.append(
                SearchResult(
                    id=task.id, content=task.content, type="task", rank=0.0, task=task, tag=tag
                )
            )

        habit_rows = conn.execute(
            """
            SELECT h.id, h.content, h.created, 0.0 as rank
            FROM habits h
            JOIN tags tg ON h.id = tg.habit_id
            WHERE tg.tag = ? COLLATE NOCASE
            """,
            (tag,),
        ).fetchall()

        results.extend(
            SearchResult(id=row[0], content=row[1], type="habit", rank=0.0, tag=tag)
            for row in habit_rows
        )

        return results[:limit]


def search_fuzzy(query: str, limit: int = 20) -> list[SearchResult]:
    """Fallback fuzzy search when FTS finds nothing."""
    if not query or not query.strip():
        return []

    results: list[SearchResult] = []

    tasks = get_tasks()
    task_match = find_in_pool(query, tasks)
    if task_match:
        results.append(
            SearchResult(
                id=task_match.id, content=task_match.content, type="task", rank=0.0, task=task_match
            )
        )

    habits = get_habits()
    habit_match = find_in_pool(query, habits)
    if habit_match:
        results.append(
            SearchResult(id=habit_match.id, content=habit_match.content, type="habit", rank=0.0)
        )

    return results[:limit]


def search_all(query: str, limit: int = 20, fuzzy_fallback: bool = True) -> list[SearchResult]:
    """Unified search: FTS with fuzzy fallback."""
    if not query or not query.strip():
        return []

    tag_prefix = query.strip().startswith("#")

    if tag_prefix:
        results = search_by_tag(query, limit)
    else:
        results: list[SearchResult] = []
        results.extend(search_tasks(query, limit))
        results.extend(search_habits(query, limit))
        results.extend(search_tags(query, limit))

        results.sort(key=lambda r: r.rank)

        if not results and fuzzy_fallback:
            results = search_fuzzy(query, limit)

    return results[:limit]

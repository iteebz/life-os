from . import db
from .habits import get_habit
from .lib import clock
from .lib.converters import row_to_task
from .models import Habit, Task
from .tags import hydrate_tags, load_tags_for_tasks
from .tasks import _task_sort_key, get_tasks

__all__ = [
    "get_day_breakdown",
    "get_day_completed",
    "get_pending_items",
    "get_today_breakdown",
    "get_today_completed",
]


def _get_checked_today() -> list[Habit]:
    """Internal: SELECT habits with checks WHERE check_date = today."""
    today_str = clock.today().isoformat()
    with db.get_db() as conn:
        cursor = conn.execute(
            """
            SELECT DISTINCT h.id, h.content, h.created
            FROM habits h
            INNER JOIN checks c ON h.id = c.habit_id
            WHERE DATE(c.check_date) = DATE(?)
            ORDER BY h.created DESC
            """,
            (today_str,),
        )
        habits = []
        for row in cursor.fetchall():
            habit_id = row[0]
            habit = get_habit(habit_id)
            if habit:
                habits.append(habit)
        return habits


def _get_completed_today() -> list[Task]:
    """Internal: SELECT completed tasks from today."""
    today_str = clock.today().isoformat()
    with db.get_db() as conn:
        cursor = conn.execute(
            "SELECT id, content, focus, scheduled_date, created, completed_at, parent_id, scheduled_time, blocked_by, description, steward, source, is_deadline FROM tasks WHERE date(completed_at) = ? AND completed_at IS NOT NULL",
            (today_str,),
        )
        tasks = [row_to_task(row) for row in cursor.fetchall()]
        task_ids = [t.id for t in tasks]
        tags_map = load_tags_for_tasks(task_ids, conn=conn)
        return hydrate_tags(tasks, tags_map)


def get_day_completed(date_str: str) -> list[Task | Habit]:
    """Get tasks and habits completed on a given date (YYYY-MM-DD)."""
    with db.get_db() as conn:
        cursor = conn.execute(
            "SELECT id, content, focus, scheduled_date, created, completed_at, parent_id, scheduled_time, blocked_by, description, steward, source, is_deadline FROM tasks WHERE date(completed_at) = ? AND completed_at IS NOT NULL",
            (date_str,),
        )
        tasks = [row_to_task(row) for row in cursor.fetchall()]
        task_ids = [t.id for t in tasks]
        tags_map = load_tags_for_tasks(task_ids, conn=conn)
        completed_tasks = hydrate_tags(tasks, tags_map)

        cursor = conn.execute(
            """
            SELECT DISTINCT h.id, h.content, h.created
            FROM habits h
            INNER JOIN checks c ON h.id = c.habit_id
            WHERE DATE(c.check_date) = DATE(?)
            """,
            (date_str,),
        )
        completed_habits: list[Habit] = []
        for row in cursor.fetchall():
            habit = get_habit(row[0])
            if habit:
                completed_habits.append(habit)

    return [*completed_tasks, *completed_habits]


def get_day_breakdown(date_str: str) -> tuple[int, int, int, int]:
    """Get breakdown stats for a given date (YYYY-MM-DD)."""
    with db.get_db() as conn:
        habits_done = conn.execute(
            "SELECT COUNT(DISTINCT habit_id) FROM checks WHERE DATE(check_date) = DATE(?)",
            (date_str,),
        ).fetchone()[0]

        tasks_done = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE date(completed_at) = ? AND completed_at IS NOT NULL",
            (date_str,),
        ).fetchone()[0]

        tasks_added = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE DATE(created) = DATE(?)",
            (date_str,),
        ).fetchone()[0]

        habits_added = conn.execute(
            "SELECT COUNT(*) FROM habits WHERE DATE(created) = DATE(?)",
            (date_str,),
        ).fetchone()[0]

        tasks_deleted = conn.execute(
            "SELECT COUNT(*) FROM deleted_tasks WHERE DATE(deleted_at) = DATE(?)",
            (date_str,),
        ).fetchone()[0]

    return habits_done, tasks_done, tasks_added + habits_added, tasks_deleted


def get_pending_items(asc: bool = True, include_steward: bool = False) -> list[Task]:
    """Get pending tasks for display. asc=True returns sorted ascending."""
    tasks = get_tasks(include_steward=include_steward)
    return sorted(tasks, key=_task_sort_key, reverse=not asc)


def get_today_completed() -> list[Task | Habit]:
    """Get tasks and habits completed today."""
    completed_tasks = _get_completed_today()
    completed_habits = _get_checked_today()
    return completed_tasks + completed_habits


def get_today_breakdown():
    """Get count of tasks and habits completed today, and items added today."""
    today_str = clock.today().isoformat()
    with db.get_db() as conn:
        cursor = conn.execute(
            "SELECT COUNT(DISTINCT habit_id) FROM checks WHERE DATE(check_date) = DATE(?)",
            (today_str,),
        )
        habits_today = cursor.fetchone()[0]

        cursor = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE DATE(created) = DATE(?)",
            (today_str,),
        )
        tasks_added = cursor.fetchone()[0]

        cursor = conn.execute(
            "SELECT COUNT(*) FROM habits WHERE DATE(created) = DATE(?)",
            (today_str,),
        )
        habits_added = cursor.fetchone()[0]

        cursor = conn.execute(
            "SELECT COUNT(*) FROM deleted_tasks WHERE DATE(deleted_at) = DATE(?)",
            (today_str,),
        )
        tasks_deleted = cursor.fetchone()[0]

    tasks_today = len(_get_completed_today())
    added_today = tasks_added + habits_added
    return habits_today, tasks_today, added_today, tasks_deleted

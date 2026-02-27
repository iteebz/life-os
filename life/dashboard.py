from . import db
from .core.models import Habit, Task
from .habits import get_habits
from .lib import clock
from .tasks import _fetch_tasks

__all__ = [
    "get_day_breakdown",
    "get_day_completed",
    "get_today_breakdown",
    "get_today_completed",
]


def _get_checked_today() -> list[Habit]:
    """Internal: SELECT habits with checks WHERE check_date = today."""
    today_str = clock.today().isoformat()
    with db.get_db() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT h.id
            FROM habits h
            INNER JOIN habit_checks c ON h.id = c.habit_id
            WHERE DATE(c.check_date) = DATE(?)
            ORDER BY h.created DESC
            """,
            (today_str,),
        ).fetchall()
    habit_ids = [r[0] for r in rows]
    return get_habits(habit_ids=habit_ids)


def _get_completed_today() -> list[Task]:
    """Internal: SELECT completed tasks from today."""
    today_str = clock.today().isoformat()
    with db.get_db() as conn:
        return _fetch_tasks(
            conn,
            "date(completed_at) = ? AND completed_at IS NOT NULL",
            (today_str,),
        )


def get_day_completed(date_str: str) -> list[Task | Habit]:
    """Get tasks and habits completed on a given date (YYYY-MM-DD)."""
    with db.get_db() as conn:
        completed_tasks = _fetch_tasks(
            conn,
            "date(completed_at) = ? AND completed_at IS NOT NULL",
            (date_str,),
        )
        habit_id_rows = conn.execute(
            """
            SELECT DISTINCT h.id
            FROM habits h
            INNER JOIN habit_checks c ON h.id = c.habit_id
            WHERE DATE(c.check_date) = DATE(?)
            """,
            (date_str,),
        ).fetchall()
    habit_ids = [r[0] for r in habit_id_rows]
    completed_habits = get_habits(habit_ids=habit_ids)
    return [*completed_tasks, *completed_habits]


def get_day_breakdown(date_str: str) -> tuple[int, int, int, int]:
    """Get breakdown stats for a given date (YYYY-MM-DD)."""
    with db.get_db() as conn:
        habits_done = conn.execute(
            "SELECT COUNT(DISTINCT habit_id) FROM habit_checks WHERE DATE(check_date) = DATE(?)",
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


def get_today_completed() -> list[Task | Habit]:
    """Get tasks and habits completed today."""
    return [*_get_completed_today(), *_get_checked_today()]


def get_today_breakdown() -> tuple[int, int, int, int]:
    """Get count of tasks and habits completed today, and items added today."""
    return get_day_breakdown(clock.today().isoformat())

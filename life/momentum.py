from datetime import date, timedelta

from . import db
from .lib import clock
from .lib.dates import parse_created_date
from .models import Weekly

__all__ = ["weekly_momentum"]


def _calculate_total_possible(active_items_data, week_start_date, week_end_date):
    total_possible = 0
    for _item_id, created_val in active_items_data:
        created_date = parse_created_date(created_val)

        if created_date > week_end_date:
            continue

        effective_start_date = max(created_date, week_start_date)

        if effective_start_date > week_end_date:
            continue

        days_active = (week_end_date - effective_start_date).days + 1

        per_day_target = 1
        total_possible += days_active * per_day_target

    return total_possible


def weekly_momentum():
    """Get weekly totals: this week, last week, prior week"""
    today = clock.today()

    this_week_start = today - timedelta(days=6)
    this_week_end = today

    last_week_start = today - timedelta(days=13)
    last_week_end = today - timedelta(days=7)

    prior_week_start = today - timedelta(days=20)
    prior_week_end = today - timedelta(days=14)

    weeks = {}

    with db.get_db() as conn:
        for week_name, start_date, end_date in [
            ("this_week", this_week_start, this_week_end),
            ("last_week", last_week_start, last_week_end),
            ("prior_week", prior_week_start, prior_week_end),
        ]:
            start_str = start_date.isoformat()
            end_str = end_date.isoformat()
            cursor = conn.execute(
                """
                SELECT COUNT(*)
                FROM tasks
                WHERE completed_at >= ?
                AND completed_at <= ?
                AND completed_at IS NOT NULL""",
                (start_str, end_str),
            )
            tasks = cursor.fetchone()[0]

            cursor = conn.execute(
                """
                SELECT COUNT(*)
                FROM habit_checks c
                WHERE c.check_date >= ?
                AND c.check_date <= ?""",
                (start_str, end_str),
            )
            habits = cursor.fetchone()[0]

            cursor = conn.execute(
                """
                SELECT COUNT(*)
                FROM tasks
                WHERE (
                    created <= ?
                    OR (completed_at >= ? AND completed_at <= ?)
                )""",
                (end_str, start_str, end_str),
            )
            tasks_total = cursor.fetchone()[0]

            cursor = conn.execute(
                """
                SELECT DISTINCT
                    h.id,
                    h.created
                FROM habits h"""
            )
            active_habits_data = cursor.fetchall()

            habits_total_possible = _calculate_total_possible(
                active_habits_data,
                date.fromisoformat(start_str),
                date.fromisoformat(end_str),
            )

            weeks[week_name] = Weekly(
                tasks_completed=tasks,
                tasks_total=tasks_total,
                habits_completed=habits,
                habits_total=habits_total_possible,
            )

    return weeks

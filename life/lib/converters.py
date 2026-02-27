import dataclasses
from datetime import date, datetime
from typing import TypeVar, cast

from life.core.models import Habit, Task

T = TypeVar("T", Task, Habit)

TaskRow = tuple[object, ...]
HabitRow = tuple[object, ...]


def _parse_date(val) -> date | None:
    """Parse a date value that may be str or numeric timestamp."""
    if isinstance(val, str) and val:
        return date.fromisoformat(val.split("T")[0])
    if isinstance(val, (int, float)):
        return datetime.fromtimestamp(val).date()
    return None


def _parse_datetime(val) -> datetime:
    """Parse a datetime value that may be str or numeric timestamp."""
    if isinstance(val, (int, float)):
        return datetime.fromtimestamp(val)
    if isinstance(val, str) and val:
        try:
            return datetime.fromisoformat(val)
        except ValueError:
            return datetime.combine(date.fromisoformat(val), datetime.min.time())
    return datetime.min


def _parse_datetime_optional(val) -> datetime | None:
    """Parse an optional datetime value that may be str or numeric timestamp."""
    if isinstance(val, str) and val:
        try:
            return datetime.fromisoformat(val)
        except ValueError:
            return datetime.combine(date.fromisoformat(val), datetime.min.time())
    elif isinstance(val, (int, float)):
        return datetime.fromtimestamp(val)
    return None


def row_to_task(row: TaskRow) -> Task:
    """
    Converts a raw database row from tasks table into a Task object.
    Expected row format: (id, content, focus, scheduled_date, created, completed, parent_id, scheduled_time, blocked_by, description, steward, source, is_deadline)
    """
    return Task(
        id=cast(str, row[0]),
        content=cast(str, row[1]),
        focus=bool(row[2]),
        scheduled_date=_parse_date(row[3]),
        created=_parse_datetime(row[4]),
        completed_at=_parse_datetime_optional(row[5]),
        parent_id=cast(str, row[6]) if len(row) > 6 and row[6] is not None else None,
        scheduled_time=cast(str, row[7]) if len(row) > 7 and row[7] is not None else None,
        blocked_by=cast(str, row[8]) if len(row) > 8 and row[8] is not None else None,
        description=cast(str, row[9]) if len(row) > 9 and row[9] is not None else None,
        steward=bool(row[10]) if len(row) > 10 and row[10] is not None else False,
        source=cast(str, row[11]) if len(row) > 11 and row[11] is not None else None,
        is_deadline=bool(row[12]) if len(row) > 12 and row[12] is not None else False,
    )


def row_to_habit(row: HabitRow) -> Habit:
    """
    Converts a raw database row from habits table into a Habit object.
    Expected row format: (id, content, created, archived_at, parent_id, private)
    """
    return Habit(
        id=cast(str, row[0]),
        content=cast(str, row[1]),
        created=_parse_datetime(row[2]),
        archived_at=_parse_datetime_optional(row[3]) if len(row) > 3 else None,
        parent_id=cast(str, row[4]) if len(row) > 4 and row[4] is not None else None,
        private=bool(row[5]) if len(row) > 5 and row[5] is not None else False,
    )


def hydrate_tags_onto[T: (Task, Habit)](item: T, tags: list[str]) -> T:
    """
    Attaches tags list to a Task or Habit object.
    Returns a new frozen dataclass instance with tags populated.
    """
    return dataclasses.replace(item, tags=tags)

from datetime import date, datetime

from life.core.models import Habit, Task
from life.lib.converters import (
    _parse_date,
    _parse_datetime,
    _parse_datetime_optional,
    hydrate_tags_onto,
    row_to_habit,
    row_to_task,
)


def test_parse_date_from_iso_string():
    result = _parse_date("2025-10-30")
    assert result == date(2025, 10, 30)


def test_parse_date_from_iso_datetime_string():
    result = _parse_date("2025-10-30T14:30:00")
    assert result == date(2025, 10, 30)


def test_parse_date_from_timestamp():
    ts = datetime(2025, 10, 30).timestamp()
    result = _parse_date(ts)
    assert result == date(2025, 10, 30)


def test_parse_date_empty_string():
    result = _parse_date("")
    assert result is None


def test_parse_date_none():
    result = _parse_date(None)
    assert result is None


def test_parse_datetime_from_iso_string():
    result = _parse_datetime("2025-10-30T14:30:00")
    assert result == datetime(2025, 10, 30, 14, 30, 0)


def test_parse_datetime_from_date_string():
    result = _parse_datetime("2025-10-30")
    assert result.date() == date(2025, 10, 30)


def test_parse_datetime_from_timestamp():
    ts = datetime(2025, 10, 30, 14, 30).timestamp()
    result = _parse_datetime(ts)
    assert result.year == 2025
    assert result.month == 10
    assert result.day == 30


def test_parse_datetime_empty_string():
    result = _parse_datetime("")
    assert result == datetime.min


def test_parse_datetime_optional_from_iso_string():
    result = _parse_datetime_optional("2025-10-30T14:30:00")
    assert result == datetime(2025, 10, 30, 14, 30, 0)


def test_parse_datetime_optional_from_timestamp():
    ts = datetime(2025, 10, 30).timestamp()
    result = _parse_datetime_optional(ts)
    assert result.date() == date(2025, 10, 30)


def test_parse_datetime_optional_empty_string():
    result = _parse_datetime_optional("")
    assert result is None


def test_parse_datetime_optional_none():
    result = _parse_datetime_optional(None)
    assert result is None


def test_row_to_task_complete():
    row = (
        "task-1",
        "Buy milk",
        1,
        "2025-10-31",
        "2025-10-30T10:00:00",
        "2025-10-30T15:00:00",
    )
    task = row_to_task(row)
    assert task.id == "task-1"
    assert task.content == "Buy milk"
    assert task.focus is True
    assert task.scheduled_date == date(2025, 10, 31)
    assert task.completed_at is not None


def test_row_to_task_no_focus():
    row = (
        "task-2",
        "Read",
        0,
        None,
        "2025-10-30T10:00:00",
        None,
    )
    task = row_to_task(row)
    assert task.focus is False
    assert task.scheduled_date is None
    assert task.completed_at is None


def test_row_to_habit_complete():
    row = (
        "habit-1",
        "Morning run",
        "2025-10-30T06:00:00",
    )
    habit = row_to_habit(row)
    assert habit.id == "habit-1"
    assert habit.content == "Morning run"
    assert habit.created.date() == date(2025, 10, 30)


def test_hydrate_tags_task():
    task = Task(
        id="task-1",
        content="Buy milk",
        focus=False,
        scheduled_date=None,
        created=datetime.now(),
        completed_at=None,
        tags=[],
    )
    hydrated = hydrate_tags_onto(task, ["urgent", "shopping"])
    assert hydrated.tags == ["urgent", "shopping"]
    assert hydrated.id == task.id


def test_hydrate_tags_habit():
    habit = Habit(
        id="habit-1",
        content="Morning run",
        created=datetime.now(),
        tags=[],
    )
    hydrated = hydrate_tags_onto(habit, ["morning", "exercise"])
    assert hydrated.tags == ["morning", "exercise"]
    assert hydrated.id == habit.id


def test_hydrate_tags_empty():
    task = Task(
        id="task-1",
        content="Task",
        focus=False,
        scheduled_date=None,
        created=datetime.now(),
        completed_at=None,
        tags=[],
    )
    hydrated = hydrate_tags_onto(task, [])
    assert hydrated.tags == []

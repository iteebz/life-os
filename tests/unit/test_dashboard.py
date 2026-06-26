from datetime import datetime, time, timedelta

import life.lib.clock as clock
import lifeos.core.lib.clock as core_clock
from life.dash import (
    get_today_breakdown,
    get_today_completed,
)
from life.habit import add_habit, get_habits, toggle_check
from life.task import add_task, check_task, get_tasks
from life.task.render import render_dashboard
from lifeos.core.lib.ansi import theme
from lifeos.core.lib.store import get_db


def test_pending_empty(tmp_life_dir):
    items = get_tasks() + get_habits()
    assert items == []


def test_pending_returns_tasks(tmp_life_dir):
    add_task("task 1")
    add_task("task 2")
    items = get_tasks() + get_habits()
    assert len(items) == 2


def test_pending_items_sort_focus_first(tmp_life_dir):
    add_task("unfocused soon", focus=False, scheduled_date="2025-01-01")
    add_task("focused later", focus=True, scheduled_date="2025-12-31")
    add_task("unfocused later", focus=False, scheduled_date="2025-12-31")

    items = get_tasks()
    assert items[0].focus is True
    assert items[0].content == "focused later"


def test_pending_items_exclude_completed(tmp_life_dir):
    task1_id = add_task("task 1")
    add_task("task 2")
    check_task(task1_id)

    items = get_tasks()
    assert len(items) == 1
    assert items[0].content == "task 2"


def test_completed_empty(tmp_life_dir, fixed_today):
    completed = get_today_completed()
    assert completed == []


def test_completed_tasks(tmp_life_dir, fixed_today):
    task1_id = add_task("task 1")
    add_task("task 2")
    check_task(task1_id)

    completed = get_today_completed()
    assert len(completed) == 1
    assert completed[0].id == task1_id


def test_completed_habits(tmp_life_dir, fixed_today):
    habit_id = add_habit("morning routine")
    toggle_check(habit_id)

    completed = get_today_completed()
    assert len(completed) == 1
    assert completed[0].id == habit_id


def test_completed_mixed(tmp_life_dir, fixed_today):
    task_id = add_task("task")
    habit_id = add_habit("habit")
    check_task(task_id)
    toggle_check(habit_id)

    completed = get_today_completed()
    assert len(completed) == 2


def test_breakdown_empty(tmp_life_dir, fixed_today):
    habits_today, tasks_today, _, _deleted = get_today_breakdown()
    assert habits_today == 0
    assert tasks_today == 0


def test_breakdown_tasks(tmp_life_dir, fixed_today):
    task1_id = add_task("task 1")
    task2_id = add_task("task 2")
    check_task(task1_id)
    check_task(task2_id)

    habits_today, tasks_today, _, _deleted = get_today_breakdown()
    assert habits_today == 0
    assert tasks_today == 2


def test_breakdown_habits(tmp_life_dir, fixed_today):
    habit1_id = add_habit("habit 1")
    habit2_id = add_habit("habit 2")
    toggle_check(habit1_id)
    toggle_check(habit2_id)

    habits_today, tasks_today, _, _deleted = get_today_breakdown()
    assert habits_today == 2
    assert tasks_today == 0


def test_breakdown_mixed(tmp_life_dir, fixed_today):
    task_id = add_task("task")
    habit1_id = add_habit("habit 1")
    habit2_id = add_habit("habit 2")
    check_task(task_id)
    toggle_check(habit1_id)
    toggle_check(habit2_id)

    habits_today, tasks_today, _, _deleted = get_today_breakdown()
    assert habits_today == 2
    assert tasks_today == 1


def test_today_completed_exclude_yesterday(tmp_life_dir, fixed_today):
    task_id = add_task("task completed yesterday")

    with get_db() as conn:
        yesterday = fixed_today - timedelta(days=1)
        conn.execute(
            "UPDATE tasks SET completed_at = ? WHERE id = ?",
            (datetime.combine(yesterday, time.min).isoformat(), task_id),
        )

    completed = get_today_completed()
    assert len(completed) == 0


def test_pending_items_all_returned(tmp_life_dir):
    add_task("task 1")
    add_task("task 2")
    add_task("task 3")

    tasks = get_tasks()
    assert len(tasks) == 3


# --- render tests ---


def _make_render_ctx(monkeypatch, fixed_now: datetime):
    monkeypatch.setattr(clock, "today", lambda: fixed_now.date())
    monkeypatch.setattr(clock, "now", lambda: fixed_now)
    monkeypatch.setattr(core_clock, "today", lambda: fixed_now.date())
    monkeypatch.setattr(core_clock, "now", lambda: fixed_now)


def test_render_past_due_habit_shows_not_red(tmp_life_dir, monkeypatch):
    _make_render_ctx(monkeypatch, datetime(2025, 10, 30, 10, 0))
    add_habit("brush", tags=["self"])
    items = get_tasks() + get_habits()
    output = render_dashboard(items, (0, 0, 0, 0))
    assert "brush" in output
    assert theme.red not in output


def test_render_dashboard_now_marker_present(tmp_life_dir, monkeypatch):
    _make_render_ctx(monkeypatch, datetime(2025, 10, 30, 9, 0))
    items = get_tasks() + get_habits()
    output = render_dashboard(items, (0, 0, 0, 0))
    assert "▸" in output


def test_render_checked_habit_not_red(tmp_life_dir, monkeypatch):
    _make_render_ctx(monkeypatch, datetime(2025, 10, 30, 10, 0))
    hid = add_habit("brush", tags=["self"])
    toggle_check(hid)
    items = get_tasks() + get_habits()
    completed = get_today_completed()
    output = render_dashboard(items, (1, 0, 0, 0), today_items=completed)
    daily_section = output.split("DAILY")[1] if "DAILY" in output else ""
    assert theme.red not in daily_section

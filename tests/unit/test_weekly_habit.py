from datetime import date, datetime, time, timedelta

import life.lib.clock as clock
from life.habit import add_habit, check_habit, get_habits, get_streak
from life.lib.store import get_db


def test_add_weekly_habit(tmp_life_dir):
    hid = add_habit("bouldering", tags=["health"], cadence="weekly")
    habits = get_habits()
    h = next(h for h in habits if h.id == hid)
    assert h.cadence == "weekly"


def test_default_cadence_is_daily(tmp_life_dir):
    hid = add_habit("shower")
    habits = get_habits()
    h = next(h for h in habits if h.id == hid)
    assert h.cadence == "daily"


def test_weekly_streak_single_week(tmp_life_dir, fixed_today):
    hid = add_habit("climb", cadence="weekly")
    check_habit(hid, check_on=fixed_today)
    assert get_streak(hid) == 1


def test_weekly_streak_consecutive_weeks(tmp_life_dir, monkeypatch):
    # Fix to a Wednesday so we have clean week boundaries
    wed = date(2026, 3, 4)  # Wednesday
    monkeypatch.setattr(clock, "today", lambda: wed)
    monkeypatch.setattr(clock, "now", lambda: datetime.combine(wed, time.min))

    hid = add_habit("climb", cadence="weekly")
    # Check this week (Wednesday)
    check_habit(hid, check_on=wed)
    # Check last week (any day)
    check_habit(hid, check_on=wed - timedelta(days=7))
    # Check 2 weeks ago
    check_habit(hid, check_on=wed - timedelta(days=14))

    assert get_streak(hid) == 3


def test_weekly_streak_gap_breaks(tmp_life_dir, monkeypatch):
    wed = date(2026, 3, 4)
    monkeypatch.setattr(clock, "today", lambda: wed)
    monkeypatch.setattr(clock, "now", lambda: datetime.combine(wed, time.min))

    hid = add_habit("climb", cadence="weekly")
    check_habit(hid, check_on=wed)
    # Skip last week, check 2 weeks ago
    check_habit(hid, check_on=wed - timedelta(days=14))

    assert get_streak(hid) == 1


def test_weekly_streak_grace_previous_week(tmp_life_dir, monkeypatch):
    """If checked last week but not yet this week, streak should be 1."""
    mon = date(2026, 3, 2)  # Monday
    monkeypatch.setattr(clock, "today", lambda: mon)
    monkeypatch.setattr(clock, "now", lambda: datetime.combine(mon, time.min))

    hid = add_habit("climb", cadence="weekly")
    # Only checked last week (Friday)
    check_habit(hid, check_on=mon - timedelta(days=3))

    assert get_streak(hid) == 1


def test_weekly_streak_zero_if_too_old(tmp_life_dir, monkeypatch):
    wed = date(2026, 3, 4)
    monkeypatch.setattr(clock, "today", lambda: wed)
    monkeypatch.setattr(clock, "now", lambda: datetime.combine(wed, time.min))

    hid = add_habit("climb", cadence="weekly")
    # Only checked 3 weeks ago — too old
    check_habit(hid, check_on=wed - timedelta(days=21))

    assert get_streak(hid) == 0


def test_weekly_streak_year_boundary(tmp_life_dir, monkeypatch):
    """Streak across Dec→Jan should work."""
    jan2 = date(2026, 1, 5)  # Monday
    monkeypatch.setattr(clock, "today", lambda: jan2)
    monkeypatch.setattr(clock, "now", lambda: datetime.combine(jan2, time.min))

    hid = add_habit("climb", cadence="weekly")
    check_habit(hid, check_on=jan2)  # week of Jan 5
    check_habit(hid, check_on=date(2025, 12, 30))  # week of Dec 29
    check_habit(hid, check_on=date(2025, 12, 23))  # week of Dec 22

    assert get_streak(hid) == 3


def test_weekly_metrics_count_one_per_week(tmp_life_dir, fixed_today):
    """Weekly habits should count as 1 possible per week, not 7."""
    from life.feedback import build_feedback_snapshot
    from life.task import get_all_tasks, get_tasks

    add_habit("daily-thing")
    add_habit("weekly-thing", cadence="weekly")

    tasks = get_tasks()
    all_tasks = get_all_tasks()
    habits = get_habits()

    snapshot = build_feedback_snapshot(
        all_tasks=all_tasks,
        pending_tasks=tasks,
        habits=habits,
        today=fixed_today,
    )
    # 1 daily habit * 7 days + 1 weekly habit * 1 week = 8
    assert snapshot.habit_possible == 8


def test_weekly_momentum_total(tmp_life_dir, fixed_today):
    """Weekly habit in momentum should be 1 per week, not 7."""
    from life.momentum import weekly_momentum

    with get_db() as conn:
        conn.execute(
            "INSERT INTO habits (id, content, created, cadence) VALUES (?, ?, ?, ?)",
            (
                "weekly_h",
                "Weekly Thing",
                datetime.combine(fixed_today - timedelta(days=30), time.min).isoformat(),
                "weekly",
            ),
        )
        conn.commit()

    momentum = weekly_momentum()
    # 1 weekly habit = 1 possible per week
    assert momentum["this_week"].habits_total == 1
    assert momentum["last_week"].habits_total == 1

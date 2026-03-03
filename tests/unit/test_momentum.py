from datetime import datetime, time, timedelta

from life.lib.store import get_db
from life.momentum import weekly_momentum


def test_rolling_7day_window(tmp_life_dir, fixed_today):
    """Calculate habits_completed and habits_total for rolling 7-day windows."""
    with get_db() as conn:
        conn.execute(
            "INSERT INTO habits (id, content, created) VALUES (?, ?, ?)",
            (
                "habit_all_weeks",
                "Habit All Weeks",
                datetime.combine(fixed_today - timedelta(days=30), time.min).isoformat(),
            ),
        )

        # Data for 'this week' (0-7 days ago)
        for i in range(7):
            check_date = fixed_today - timedelta(days=i)
            conn.execute(
                "INSERT INTO checks (habit_id, check_date, completed_at) VALUES (?, ?, ?)",
                ("habit_all_weeks", check_date.isoformat(), check_date.isoformat()),
            )

        # Data for 'last week' (7-14 days ago)
        for i in range(7, 14):
            check_date = fixed_today - timedelta(days=i)
            conn.execute(
                "INSERT INTO checks (habit_id, check_date, completed_at) VALUES (?, ?, ?)",
                ("habit_all_weeks", check_date.isoformat(), check_date.isoformat()),
            )

        # Data for 'prior week' (14-21 days ago)
        for i in range(14, 21):
            check_date = fixed_today - timedelta(days=i)
            conn.execute(
                "INSERT INTO checks (habit_id, check_date, completed_at) VALUES (?, ?, ?)",
                ("habit_all_weeks", check_date.isoformat(), check_date.isoformat()),
            )
        conn.commit()

    momentum_data = weekly_momentum()

    # Assert 'this_week' (0-7 days ago)
    this_week = momentum_data["this_week"]
    assert this_week.habits_completed == 7
    assert this_week.habits_total == 7

    # Assert 'last_week' (7-14 days ago)
    last_week = momentum_data["last_week"]
    assert last_week.habits_completed == 7
    assert last_week.habits_total == 7

    # Assert 'prior_week' (14-21 days ago)
    prior_week = momentum_data["prior_week"]
    assert prior_week.habits_completed == 7
    assert prior_week.habits_total == 7


def test_count_one_per_day(tmp_life_dir, fixed_today):
    """Count habits as 1 check per day for total possible calculations."""

    with get_db() as conn:
        conn.execute(
            "INSERT INTO habits (id, content, created) VALUES (?, ?, ?)",
            (
                "habit_multi_target",
                "Habit Multi Target",
                datetime.combine(fixed_today - timedelta(days=6), time.min).isoformat(),
            ),
        )
        conn.commit()

    momentum_data = weekly_momentum()

    this_week = momentum_data["this_week"]
    assert this_week.habits_total == 7

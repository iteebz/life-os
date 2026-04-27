from life.domain.habit import (
    add_habit,
    get_checks,
    get_habits,
    toggle_check,
)


def test_add_check_habit(tmp_life_dir):
    habit_id = add_habit("daily standup")
    toggle_check(habit_id)


def test_check_idempotent(tmp_life_dir):
    habit_id = add_habit("meditation")
    toggle_check(habit_id)
    checks = get_checks(habit_id)
    assert len(checks) == 1
    pending_habits = get_habits()
    assert any(habit.id == habit_id for habit in pending_habits)


def test_pending_habit_visible(tmp_life_dir):
    iid = add_habit("a habit")
    habits = get_habits()
    assert len(habits) == 1
    assert habits[0].id == iid


def test_check_once_per_day(tmp_life_dir):
    iid = add_habit("a habit")
    toggle_check(iid)
    checks = get_checks(iid)
    assert len(checks) == 1
    habits = get_habits()
    assert len(habits) == 1
    assert habits[0].id == iid


def test_check_to_completion(tmp_life_dir):
    iid = add_habit("5x")
    toggle_check(iid)
    habits = get_habits()
    assert len(habits) == 1
    assert habits[0].id == iid

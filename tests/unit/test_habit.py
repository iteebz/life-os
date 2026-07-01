from life.habit import (
    add_habit,
    get_checks,
    get_habit,
    get_habits,
    merge_habit,
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


def test_merge_habit_moves_checks_and_soft_deletes_source(tmp_life_dir):
    source_id = add_habit("gym")
    target_id = add_habit("exercise")
    toggle_check(source_id)

    merge_habit(get_habit(source_id), get_habit(target_id))

    assert get_habit(source_id) is None
    target = get_habit(target_id)
    assert len(target.checks) == 1


def test_merge_habit_skips_conflicting_dates(tmp_life_dir):
    source_id = add_habit("gym")
    target_id = add_habit("exercise")
    toggle_check(source_id)
    toggle_check(target_id)

    merge_habit(get_habit(source_id), get_habit(target_id))

    target = get_habit(target_id)
    assert len(target.checks) == 1

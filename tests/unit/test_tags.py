import pytest
from life.tags import (
    add_tag,
    get_habits_by_tag,
    get_tags_for_habit,
    get_tags_for_task,
    get_tasks_by_tag,
    list_all_tags,
    remove_tag,
)

from life.habits import add_habit
from life.tasks import add_task


def test_add_tag_to_task(tmp_life_dir):
    task_id = add_task("task with tag")
    add_tag(task_id=task_id, habit_id=None, tag="urgent")
    tags = get_tags_for_task(task_id)
    assert "urgent" in tags


def test_add_tag_to_habit(tmp_life_dir):
    habit_id = add_habit("habit with tag")
    add_tag(task_id=None, habit_id=habit_id, tag="morning")
    tags = get_tags_for_habit(habit_id)
    assert "morning" in tags


def test_tag_case_insensitive(tmp_life_dir):
    task_id = add_task("task")
    add_tag(task_id=task_id, habit_id=None, tag="URGENT")
    tags = get_tags_for_task(task_id)
    assert "urgent" in tags


def test_duplicate_tag_idempotent(tmp_life_dir):
    task_id = add_task("task")
    add_tag(task_id=task_id, habit_id=None, tag="work")
    add_tag(task_id=task_id, habit_id=None, tag="work")
    tags = get_tags_for_task(task_id)
    assert len(tags) >= 1 and "work" in tags


def test_get_tasks_by_tag(tmp_life_dir):
    task1_id = add_task("task 1")
    task2_id = add_task("task 2")
    add_task("untagged task")

    add_tag(task_id=task1_id, habit_id=None, tag="priority")
    add_tag(task_id=task2_id, habit_id=None, tag="priority")

    tasks = get_tasks_by_tag("priority")
    assert len(tasks) == 2
    assert any(t.id == task1_id for t in tasks)
    assert any(t.id == task2_id for t in tasks)


def test_get_habits_by_tag(tmp_life_dir):
    habit1_id = add_habit("habit 1")
    habit2_id = add_habit("habit 2")
    add_habit("untagged habit")

    add_tag(task_id=None, habit_id=habit1_id, tag="daily")
    add_tag(task_id=None, habit_id=habit2_id, tag="daily")

    habits = get_habits_by_tag("daily")
    assert len(habits) == 2
    assert any(h.id == habit1_id for h in habits)
    assert any(h.id == habit2_id for h in habits)


def test_remove_tag_from_task(tmp_life_dir):
    task_id = add_task("task")
    add_tag(task_id=task_id, habit_id=None, tag="work")
    remove_tag(task_id=task_id, habit_id=None, tag="work")
    tags = get_tags_for_task(task_id)
    assert len(tags) == 0


def test_remove_tag_from_habit(tmp_life_dir):
    habit_id = add_habit("habit")
    add_tag(task_id=None, habit_id=habit_id, tag="morning")
    remove_tag(task_id=None, habit_id=habit_id, tag="morning")
    tags = get_tags_for_habit(habit_id)
    assert len(tags) == 0


def test_list_all_tags(tmp_life_dir):
    task_id = add_task("task")
    habit_id = add_habit("habit")

    add_tag(task_id=task_id, habit_id=None, tag="urgent")
    add_tag(task_id=None, habit_id=habit_id, tag="daily")
    add_tag(task_id=task_id, habit_id=None, tag="work")

    all_tags = list_all_tags()
    assert set(all_tags) == {"urgent", "daily", "work"}
    assert all_tags == sorted(all_tags)


def test_add_tag_requires_one_id(tmp_life_dir):
    with pytest.raises(ValueError):
        add_tag(task_id=None, habit_id=None, tag="test")

    with pytest.raises(ValueError):
        add_tag(task_id="task_id", habit_id="habit_id", tag="test")


def test_remove_tag_requires_one_id(tmp_life_dir):
    with pytest.raises(ValueError):
        remove_tag(task_id=None, habit_id=None, tag="test")

    with pytest.raises(ValueError):
        remove_tag(task_id="task_id", habit_id="habit_id", tag="test")


def test_query_by_tag_case_insensitive(tmp_life_dir):
    task_id = add_task("task")
    add_tag(task_id=task_id, habit_id=None, tag="URGENT")

    tasks = get_tasks_by_tag("urgent")
    assert len(tasks) == 1
    assert tasks[0].id == task_id


def test_nonexistent_task_tags_empty(tmp_life_dir):
    tags = get_tags_for_task("nonexistent")
    assert tags == []


def test_nonexistent_habit_tags_empty(tmp_life_dir):
    tags = get_tags_for_habit("nonexistent")
    assert tags == []

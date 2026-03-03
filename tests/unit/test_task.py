from life.task import (
    add_task,
    check_task,
    delete_task,
    get_task,
    get_tasks,
    update_task,
)


def test_add_task_creates_task(tmp_life_dir):
    task_id = add_task("test task")
    assert task_id is not None
    task = get_task(task_id)
    assert task is not None
    assert task.content == "test task"


def test_add_task_with_focus(tmp_life_dir):
    task_id = add_task("focused task", focus=True)
    task = get_task(task_id)
    assert task.focus is True


def test_add_task_with_due(tmp_life_dir):
    task_id = add_task("due task", scheduled_date="2025-12-31")
    task = get_task(task_id)
    assert str(task.scheduled_date) == "2025-12-31"


def test_add_task_with_tags(tmp_life_dir):
    task_id = add_task("tagged task", tags=["urgent", "work"])
    task = get_task(task_id)
    assert "urgent" in task.tags
    assert "work" in task.tags


def test_pending_tasks_sort_order(tmp_life_dir):
    add_task("task 1")
    add_task("task 2")
    tasks = get_tasks()
    assert len(tasks) == 2


def test_complete_task(tmp_life_dir):
    task_id = add_task("task to complete")
    check_task(task_id)
    pending = get_tasks()
    assert not any(t.id == task_id for t in pending)


def test_get_focus_tasks(tmp_life_dir):
    task_id = add_task("focused", focus=True)
    add_task("unfocused", focus=False)
    focus_tasks = [t for t in get_tasks() if t.focus]
    assert len(focus_tasks) == 1
    assert focus_tasks[0].id == task_id


def test_update_task_content(tmp_life_dir):
    task_id = add_task("original")
    update_task(task_id, content="updated")
    task = get_task(task_id)
    assert task.content == "updated"


def test_update_task_focus(tmp_life_dir):
    task_id = add_task("task", focus=False)
    update_task(task_id, focus=True)
    task = get_task(task_id)
    assert task.focus is True


def test_update_task_due(tmp_life_dir):
    task_id = add_task("task", scheduled_date="2025-12-31")
    update_task(task_id, scheduled_date="2025-01-01")
    task = get_task(task_id)
    assert str(task.scheduled_date) == "2025-01-01"


def test_delete_task(tmp_life_dir):
    task_id = add_task("task to delete")
    delete_task(task_id)
    task = get_task(task_id)
    assert task is None


def test_sort_by_focus(tmp_life_dir):
    add_task("unfocused", focus=False)
    add_task("focused", focus=True)
    tasks = get_tasks()
    assert tasks[0].focus is True


def test_sort_by_due(tmp_life_dir):
    add_task("later", scheduled_date="2025-12-31")
    add_task("sooner", scheduled_date="2025-01-01")
    tasks = get_tasks()
    assert str(tasks[0].scheduled_date) == "2025-01-01"


def test_focus_priority_over_due(tmp_life_dir):
    add_task("unfocused soon", focus=False, scheduled_date="2025-01-01")
    add_task("focused later", focus=True, scheduled_date="2025-12-31")
    tasks = get_tasks()
    assert tasks[0].focus is True

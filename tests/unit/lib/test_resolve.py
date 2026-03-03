from life.lib.resolve import resolve_item, resolve_item_any, resolve_task
from life.task import add_task, check_task


def test_resolve_task_finds_pending(tmp_life_dir):
    add_task("call the bank", tags=["finance"])
    task = resolve_task("call bank")
    assert task.content == "call the bank"


def test_resolve_task_finds_completed_today(tmp_life_dir):
    task_id = add_task("completed today", tags=["finance"])
    check_task(task_id)
    task = resolve_task("completed today")
    assert task.id == task_id


def test_resolve_item_finds_completed_today(tmp_life_dir):
    task_id = add_task("completed item", tags=["finance"])
    check_task(task_id)
    task, _ = resolve_item("completed item")
    assert task.id == task_id


def test_resolve_item_any_finds_completed(tmp_life_dir):
    task_id = add_task("done task", tags=["finance"])
    check_task(task_id)
    task, _ = resolve_item_any("done task")
    assert task is not None
    assert task.id == task_id


def test_resolve_item_any_prefers_pending(tmp_life_dir):
    pending_id = add_task("invoice jeff", tags=["finance"])
    completed_id = add_task("invoice jeff old", tags=["finance"])
    check_task(completed_id)
    task, _ = resolve_item_any("invoice jeff")
    assert task.id == pending_id


def test_resolve_item_finds_today_completed(tmp_life_dir):
    add_task("pending task", tags=["finance"])
    completed_id = add_task("completed task", tags=["finance"])
    check_task(completed_id)
    task, _ = resolve_item("pending task")
    assert task is not None
    task, _ = resolve_item("completed task")
    assert task.id == completed_id

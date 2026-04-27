from life.core.errors import NotFoundError
from life.core.models import Habit, Task
from life.task import find_task, find_task_any, find_task_exact

__all__ = [
    "resolve_item",
    "resolve_item_any",
    "resolve_item_exact",
    "resolve_task",
]


def resolve_task(ref: str) -> Task:
    task = find_task_exact(ref)
    if not task:
        task = find_task(ref)
        if task:
            print(f"→ matched: {task.content}")
    if not task:
        raise NotFoundError(f"no task found: '{ref}'")
    return task


def _find_item(ref: str, find_task_fn) -> tuple[Task | None, Habit | None]:
    from life.domain.habit import find_habit

    task = find_task_fn(ref)
    habit = find_habit(ref) if not task else None
    return task, habit


def resolve_item(ref: str) -> tuple[Task | None, Habit | None]:
    task, habit = _find_item(ref, find_task)
    if not task and not habit:
        raise NotFoundError(f"No item found: '{ref}'")
    return task, habit


def resolve_item_any(ref: str) -> tuple[Task | None, Habit | None]:
    task, habit = _find_item(ref, find_task)
    if not task and not habit:
        task, _ = _find_item(ref, find_task_any)
    if not task and not habit:
        raise NotFoundError(f"No item found: '{ref}'")
    return task, habit


def resolve_item_exact(ref: str) -> tuple[Task | None, Habit | None]:
    from life.domain.habit import find_habit_exact

    task, habit = _find_item(ref, find_task_exact)
    if not task:
        habit = find_habit_exact(ref)
    if not task and not habit:
        raise NotFoundError(f"No item found: '{ref}'")
    return task, habit

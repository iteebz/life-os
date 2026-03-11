from fncli import UsageError, cli

from .core.errors import NotFoundError, ValidationError
from .core.models import Task
from .habit import add_habit, check_habit_cmd, rename_habit
from .lib import ansi
from .lib.format import render_done_row, render_row, render_uncheck_row
from .lib.parsing import validate_content
from .lib.resolve import resolve_item, resolve_item_any
from .task import (
    add_task,
    check_task_cmd,
    delete_task,
    rename_task,
    uncheck_task,
)


@cli("life", name="done", flags={"date": ["-d", "--date"], "time": ["-t", "--time"]})
def check(ref: list[str], date: str | None = None, time: str | None = None) -> None:
    """Toggle done"""
    from .habit import check_habit, get_checks, toggle_check
    from .lib.clock import today
    from .lib.dates import parse_due_date

    item_ref = " ".join(ref) if ref else ""
    if not item_ref:
        raise UsageError("Usage: life check <item>")

    if date is not None:
        from datetime import date as date_type

        parsed = parse_due_date(date)
        if not parsed:
            raise UsageError(f"Unrecognized date '{date}' — use yesterday, YYYY-MM-DD, etc.")
        check_on = date_type.fromisoformat(parsed)
        task, habit = resolve_item_any(item_ref)
        if task and not habit:
            if task.completed_at:
                raise UsageError("task is already done — uncheck first to re-complete with a date")
            check_task_cmd(task, completed_at=f"{parsed}T23:59:59")
            return
        if not habit:
            raise UsageError("item not found")
        from .habit import uncheck_habit

        checks = get_checks(habit.id)
        already_checked = any(c.date() == check_on for c in checks)
        if already_checked:
            uncheck_habit(habit.id, check_on=check_on)
            render_uncheck_row(
                f"{habit.content.lower()} ({parsed})", habit.tags, habit.id, is_habit=True
            )
        else:
            check_habit(habit.id, check_on=check_on, check_time=time)
            render_done_row(
                f"{habit.content.lower()} ({parsed})",
                time or "",
                habit.tags,
                habit.id,
                is_habit=True,
            )
        return

    task, habit = resolve_item_any(item_ref)
    if habit:
        today_date = today()
        checks = get_checks(habit.id)
        checked_today = any(c.date() == today_date for c in checks)
        if checked_today:
            updated = toggle_check(habit.id)
            if updated:
                checked_today = any(c.date() == today() for c in updated.checks)
                if not checked_today:
                    render_uncheck_row(habit.content.lower(), habit.tags, habit.id, is_habit=True)
        else:
            check_habit_cmd(habit, check_time=time)
    elif task:
        if task.completed_at:
            uncheck_task(task.id)
            render_uncheck_row(task.content.lower(), task.tags, task.id)
        else:
            check_task_cmd(task)


@cli("life", name="rm")
def rm(ref: list[str], hard: bool = False) -> None:
    """Delete item"""
    from .habit import delete_habit

    item_ref = " ".join(ref) if ref else ""
    if not item_ref:
        raise UsageError("Usage: life rm <item>")
    task, habit = resolve_item_any(item_ref)
    if task:
        delete_task(task.id, hard=hard)
        print(ansi.strikethrough(task.content))
    elif habit:
        delete_habit(habit.id)
        print(ansi.strikethrough(habit.content))


def add(
    content: list[str],
    habit: bool = False,
    focus: bool = False,
    due: str | None = None,
    tag: list[str] | None = None,
    under: str | None = None,
    desc: str | None = None,
    done: bool = False,
    steward: bool = False,
    source: str | None = None,
) -> None:
    """Add task or habit (--habit)"""
    content_str = " ".join(content) if content else ""
    try:
        validate_content(content_str)
    except ValueError as e:
        raise ValidationError(str(e)) from e

    if habit:
        from .lib.resolve import resolve_habit

        parent_id = None
        if under:
            parent = resolve_habit(under)
            if not parent:
                raise NotFoundError(f"no habit found matching '{under}'")
            parent_id = parent.id
        tags = list(tag) if tag else []
        habit_id = add_habit(content_str, tags=tags, parent_id=parent_id)
        render_row(content_str.lower(), tags, habit_id, symbol=ansi.purple("○"))
        return

    from .lib.resolve import resolve_task

    resolved_due = None
    resolved_time = None
    if due:
        from .lib.parsing import parse_due_datetime

        resolved_due, resolved_time = parse_due_datetime(due)
    parent_id = None
    if under:
        parent_task = resolve_task(under)
        if parent_task.parent_id:
            raise ValidationError("subtasks cannot have subtasks")
        parent_id = parent_task.id
    tags = list(tag) if tag else []
    if focus and parent_id:
        raise ValidationError("cannot focus a subtask — set focus on the parent")
    task_id = add_task(
        content_str,
        focus=focus,
        scheduled_date=resolved_due,
        scheduled_time=resolved_time,
        tags=tags,
        parent_id=parent_id,
        notes=desc,
        steward=steward,
        source=source,
    )
    if done:
        from .task import get_task

        task = get_task(task_id)
        if task:
            check_task_cmd(task)
        return
    symbol = ansi.bold("\u29bf") if focus else "\u25a1"
    prefix = "  └ " if parent_id else "  "
    render_row(content_str.lower(), tags, task_id, symbol=symbol, prefix=prefix)


@cli("life")
def rename(ref: list[str], to: str) -> None:
    """Rename item"""
    if not to:
        raise ValidationError("'to' content cannot be empty")
    item_ref = " ".join(ref) if ref else ""
    task, habit = resolve_item(item_ref)
    if not task and not habit:
        raise NotFoundError("item not found")
    if isinstance(task, Task):
        rename_task(task, to)
        render_uncheck_row(to, task.tags, task.id)
    elif habit:
        rename_habit(habit, to)
        render_uncheck_row(to, habit.tags, habit.id, is_habit=True)

import json as _json
from datetime import date as _date
from typing import Any

from fncli import UsageError, cli

from life.core.errors import ConflictError, ValidationError
from life.core.types import UNSET
from life.habit import update_habit
from life.lib import ansi, clock
from life.lib.clock import today as _today
from life.lib.format import format_status, format_task
from life.lib.parsing import parse_due_and_item
from life.lib.resolve import resolve_item, resolve_task
from life.render import render_task_detail

from .domain import (
    cancel_task,
    defer_task,
    find_task,
    find_task_exact,
    get_all_tasks,
    get_mutations,
    get_subtasks,
    get_task,
    get_tasks,
    set_blocked_by,
    toggle_focus,
    update_task,
)


def _fmt_date_label(date_str: str) -> str:
    d = _date.fromisoformat(date_str)
    delta = (d - clock.today()).days
    if delta == 0:
        return "today"
    if delta == 1:
        return "tomorrow"
    return f"{d.day:02d}/{d.month:02d}"


def _schedule(args: list[str], remove: bool = False) -> None:
    if remove:
        if not args:
            raise UsageError("Usage: life schedule --remove <item>")
        try:
            _, _, item_name = parse_due_and_item(list(args), remove=True)
        except ValueError as e:
            raise UsageError(str(e)) from e
        task, habit = resolve_item(item_name)
        if habit:
            update_habit(habit.id, clear_time=True)
            print(format_status("\u25a1", habit.content, habit.id))
        else:
            if not task:
                raise UsageError(f"item not found: {item_name}")
            update_task(task.id, scheduled_date=None, scheduled_time=None, is_deadline=False)
            print(format_status("\u25a1", task.content, task.id))
        return
    try:
        date_str, time_str, item_name = parse_due_and_item(list(args))
    except ValueError as e:
        raise UsageError(str(e)) from e
    if not date_str and not time_str:
        raise UsageError(
            "Schedule spec required: today, tomorrow, day name, YYYY-MM-DD, HH:MM, or 'now'"
        )
    task, habit = resolve_item(item_name)
    if habit:
        if not time_str:
            raise UsageError("Habits only support time scheduling: life schedule 07:30 <habit>")
        update_habit(habit.id, scheduled_time=time_str)
        print(format_status(ansi.muted(time_str), habit.content, habit.id))
        return
    if not task:
        raise UsageError(f"item not found: {item_name}")
    updates: dict[str, Any] = {"is_deadline": False}
    if date_str:
        updates["scheduled_date"] = date_str
    if time_str:
        updates["scheduled_time"] = time_str
    update_task(task.id, **updates)
    if time_str:
        label = ansi.muted(time_str)
    else:
        label = ansi.muted(_fmt_date_label(date_str or ""))
    print(format_status(label, task.content, task.id))


@cli("life")
def focus(ref: list[str]) -> None:
    """Pin task"""
    item_ref = " ".join(ref) if ref else ""
    if not item_ref:
        raise UsageError("Usage: life focus <item>")
    t = resolve_task(item_ref)
    toggle_focus(t.id)
    symbol = ansi.bold("\u29bf") if not t.focus else "\u25a1"
    print(format_status(symbol, t.content, t.id))


@cli("life", flags={"remove": ["-r", "--remove"]})
def due(ref: list[str], when: str, remove: bool = False) -> None:
    """Mark task deadline"""
    args = ref if remove else [when, *ref]
    try:
        date_str, time_str, item_name = parse_due_and_item(args, remove=remove)
    except ValueError as e:
        raise UsageError(str(e)) from e
    t = resolve_task(item_name)
    if remove:
        update_task(t.id, scheduled_date=None, scheduled_time=None, is_deadline=False)
        print(format_status("\u25a1", t.content, t.id))
        return
    if not date_str and not time_str:
        raise UsageError(
            "Due spec required: today, tomorrow, day name, YYYY-MM-DD, HH:MM, 'now', or -r to clear"
        )
    updates: dict[str, Any] = {"is_deadline": True}
    if date_str:
        updates["scheduled_date"] = date_str
    if time_str:
        updates["scheduled_time"] = time_str
    update_task(t.id, **updates)
    if time_str:
        label = ansi.coral(time_str)
    else:
        label = ansi.coral(_fmt_date_label(date_str or ""))
    print(format_status(label, t.content, t.id))


@cli(
    "life",
    name="set",
    flags={
        "ref": [],
        "parent": ["-p", "--parent"],
        "content": ["-c", "--content"],
        "notes": ["-n", "--notes"],
    },
)
def set_cmd(
    ref: list[str],
    parent: str | None = None,
    content: str | None = None,
    notes: str | None = None,
) -> None:
    """Set parent, content, or notes on task"""
    item_ref = " ".join(ref) if ref else ""
    if not item_ref:
        raise UsageError("Usage: life set <task> [-p parent] [-c content]")
    t = resolve_task(item_ref)
    parent_id: str | None = None
    has_update = False
    if parent is not None:
        parent_task = resolve_task(parent)
        if parent_task.parent_id:
            raise ValidationError("subtasks cannot have subtasks")
        if parent_task.id == t.id:
            raise ValidationError("a task cannot be its own parent")
        if t.focus:
            raise ValidationError("cannot parent a focused task — unfocus first")
        parent_id = parent_task.id
        has_update = True
    if content is not None:
        if not content.strip():
            raise ValidationError("content cannot be empty")
        has_update = True
    task_notes: str | None = None
    if notes is not None:
        task_notes = notes if notes != "" else None
        has_update = True
    if not has_update:
        raise UsageError("Nothing to set. Use -p for parent, -c for content, or --notes for notes.")
    update_task(
        t.id,
        content=content,
        parent_id=parent_id if parent is not None else UNSET,
        notes=task_notes if notes is not None else UNSET,
    )
    updated = resolve_task(content or item_ref)
    prefix = "  \u2514 " if updated.parent_id else ""
    print(f"{prefix}{format_status('\u25a1', updated.content, updated.id)}")


@cli("life", flags={"json": ["-j"]})
def show(ref: list[str], json: bool = False) -> None:
    """Show full task detail"""
    item_ref = " ".join(ref) if ref else ""
    if not item_ref:
        raise UsageError("Usage: life show <task>")
    t = resolve_task(item_ref)
    if json:
        print(
            _json.dumps(
                {
                    "id": t.id,
                    "content": t.content,
                    "tags": t.tags,
                    "scheduled_date": t.scheduled_date.isoformat() if t.scheduled_date else None,
                    "scheduled_time": t.scheduled_time,
                    "focus": t.focus,
                    "parent_id": t.parent_id,
                    "blocked_by": t.blocked_by,
                    "notes": t.notes,
                }
            )
        )
        return
    if t.parent_id:
        parent = get_task(t.parent_id)
        parent_subtasks = get_subtasks(t.parent_id) if parent else []
        mutations = get_mutations(t.parent_id) if parent else []
        print(render_task_detail(t, [], mutations, parent=parent, parent_subtasks=parent_subtasks))
    else:
        subtasks = get_subtasks(t.id)
        mutations = get_mutations(t.id)
        print(render_task_detail(t, subtasks, mutations))


@cli("life", flags={"by": ["-b", "--by"]})
def block(ref: list[str], by: str) -> None:
    """Mark task as blocked"""
    t = resolve_task(" ".join(ref))
    blocker = resolve_task(by)
    if blocker.id == t.id:
        raise ValidationError("a task cannot block itself")
    set_blocked_by(t.id, blocker.id)
    print(f"\u2298 {t.content.lower()}  \u2190  {blocker.content.lower()}")


@cli("life")
def unblock(ref: list[str]) -> None:
    """Clear task block"""
    t = resolve_task(" ".join(ref))
    if not t.blocked_by:
        raise ConflictError(f"'{t.content}' is not blocked")
    set_blocked_by(t.id, None)
    print(f"\u25a1 {t.content.lower()}  unblocked")


@cli("life", flags={"reason": ["-r", "--reason"]})
def cancel(ref: list[str], reason: str) -> None:
    """Cancel task with reason"""
    t = resolve_task(" ".join(ref))
    cancel_task(t.id, reason)
    print(f"\u2717 {t.content.lower()} \u2014 {reason}")


@cli("life", flags={"reason": ["-r", "--reason"]})
def defer(ref: list[str], reason: str) -> None:
    """Defer task with reason"""
    t = resolve_task(" ".join(ref))
    defer_task(t.id, reason)
    print(f"\u2192 {t.content.lower()} deferred: {reason}")


@cli(
    "life",
    help={
        "ref": (
            "[DATE] [TIME] <task>  e.g. '14:00 call jeff', "
            "'tomorrow 14:00 call jeff', '2026-03-01 09:00 dentist'"
        )
    },
)
def schedule(ref: list[str], remove: bool = False) -> None:
    """Schedule task"""
    if remove:
        _schedule(ref, remove=True)
    elif ref:
        _schedule(ref)
    else:
        raise UsageError("Usage: life schedule <ref> <when>  or  --remove")


@cli("life", flags={"ref": []})
def unschedule(ref: list[str] | None = None, overdue: bool = False) -> None:
    """Clear schedule from tasks, returning them to backlog"""
    if overdue:
        today_date = _today()
        tasks = [t for t in get_all_tasks() if t.scheduled_date and t.scheduled_date < today_date]
        if not tasks:
            print("No overdue tasks.")
            return
        for t in tasks:
            update_task(t.id, scheduled_date=None, scheduled_time=None, is_deadline=False)
            print(format_status("\u25a1", t.content, t.id))
        return

    if not ref:
        raise UsageError("Usage: life unschedule <task> [task...]  or  --overdue")

    for r in ref:
        t = resolve_task(r)
        update_task(t.id, scheduled_date=None, scheduled_time=None, is_deadline=False)
        print(format_status("\u25a1", t.content, t.id))


@cli("life", flags={"ref": [], "tag": ["-t", "--tag"], "schedule": ["-s", "--schedule"]})
def task(
    ref: list[str] | None = None,
    tag: list[str] | None = None,
    due: str | None = None,
    focus: bool = False,
    schedule: str | None = None,
    done: bool = False,
) -> None:
    """List tasks, or create one: `life task "name" -t tag`"""
    if not ref:
        tasks = get_tasks()
        if not tasks:
            print("no tasks")
        else:
            for t in tasks:
                print(f"  \u25a1 {format_task(t, tags=t.tags, show_id=True)}")
        return

    # Try to resolve as existing task — if found, update it instead of creating
    item_ref = " ".join(ref)
    existing = find_task_exact(item_ref) or find_task(item_ref)
    if existing:
        updates: dict[str, Any] = {}
        when = due or schedule
        if when:
            date_str, time_str, _ = parse_due_and_item([*when.split(), "x"])
            if date_str:
                updates["scheduled_date"] = date_str
            if time_str:
                updates["scheduled_time"] = time_str
        if updates:
            update_task(existing.id, **updates)
        print(format_status("\u25a1", existing.content, existing.id))
        return

    if not tag:
        raise UsageError('Tag required: life task "name" -t <tag>')
    from life.item import add as _add  # noqa: PLC0415 — circular: item imports task

    _add(ref, tag=tag, due=due or schedule, focus=focus, done=done)

import contextlib
import re
import sqlite3
import uuid
from datetime import date as _date
from datetime import datetime
from typing import Any

from fncli import UsageError, cli

from . import db
from .lib import clock
from .lib.ansi import ANSI
from .lib.converters import row_to_task
from .lib.errors import exit_error
from .lib.format import animate_check, format_status
from .lib.fuzzy import find_in_pool, find_in_pool_exact
from .lib.parsing import parse_due_and_item
from .models import Task, TaskMutation
from .tag import add_tag, hydrate_tags, load_tags_for_tasks

__all__ = [
    "add_task",
    "cancel_task",
    "check_task",
    "check_task_cmd",
    "defer_task",
    "delete_task",
    "find_task",
    "find_task_any",
    "find_task_exact",
    "get_all_tasks",
    "get_mutations",
    "get_subtasks",
    "get_task",
    "get_tasks",
    "last_completion",
    "rename_task",
    "set_blocked_by",
    "toggle_focus",
    "uncheck_task",
    "update_task",
]


# ── domain ───────────────────────────────────────────────────────────────────

_TASK_COLS = "id, content, focus, scheduled_date, created, completed_at, parent_id, scheduled_time, blocked_by, description, steward, source, is_deadline"


def _fetch_tasks(
    conn: sqlite3.Connection, where: str, params: tuple[object, ...] = ()
) -> list[Task]:
    cursor = conn.execute(f"SELECT {_TASK_COLS} FROM tasks WHERE {where}", params)  # noqa: S608
    tasks = [row_to_task(row) for row in cursor.fetchall()]
    task_ids = [t.id for t in tasks]
    tags_map = load_tags_for_tasks(task_ids, conn=conn)
    return hydrate_tags(tasks, tags_map)


def _task_sort_key(task: Task) -> tuple[bool, bool, object, object]:
    return (
        not task.focus,
        task.scheduled_date is None,
        task.scheduled_date,
        task.created,
    )


_AUTOTAG_PATTERNS = {
    "comms": re.compile(
        r"\b(call|message|whatsapp|email|voicemail|reply|text|telegram|signal)\b", re.IGNORECASE
    ),
    "finance": re.compile(
        r"\b(invoice|pay|transfer|liquidate|buy|order|purchase|refund|deposit)\b", re.IGNORECASE
    ),
    "health": re.compile(
        r"\b(dentist|doctor|physio|health|medical|pharmacy|chemist)\b", re.IGNORECASE
    ),
}


def _autotag(content: str, existing_tags: list[str] | None) -> list[str]:
    if existing_tags is None:
        existing_tags = []
    existing_normalized = [t.lstrip("#") for t in existing_tags]
    content_lower = content.lower()
    new_tags = []
    for tag, pattern in _AUTOTAG_PATTERNS.items():
        if tag not in existing_normalized and pattern.search(content_lower):
            new_tags.append(tag)
    return new_tags


def add_task(
    content: str,
    focus: bool = False,
    scheduled_date: str | None = None,
    tags: list[str] | None = None,
    parent_id: str | None = None,
    description: str | None = None,
    steward: bool = False,
    source: str | None = None,
) -> str:
    task_id = str(uuid.uuid4())
    with db.get_db() as conn:
        try:
            conn.execute(
                "INSERT INTO tasks (id, content, focus, scheduled_date, created, parent_id, description, steward, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    task_id,
                    content,
                    focus,
                    scheduled_date,
                    clock.today().isoformat(),
                    parent_id,
                    description,
                    steward,
                    source,
                ),
            )
        except sqlite3.IntegrityError as e:
            raise ValueError(f"Failed to add task: {e}") from e

        all_tags = list(tags or [])
        all_tags.extend(_autotag(content, all_tags))

        for tag in all_tags:
            add_tag(task_id, None, tag, conn=conn)
    return task_id


def get_task(task_id: str) -> Task | None:
    with db.get_db() as conn:
        cursor = conn.execute(
            f"SELECT {_TASK_COLS} FROM tasks WHERE id = ?",  # noqa: S608
            (task_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        task = row_to_task(row)
        tags_map = load_tags_for_tasks([task_id], conn=conn)
        return hydrate_tags([task], tags_map)[0]


def get_tasks(include_steward: bool = False) -> list[Task]:
    where = "completed_at IS NULL" if include_steward else "completed_at IS NULL AND steward = 0"
    with db.get_db() as conn:
        tasks = _fetch_tasks(conn, where)
    return sorted(tasks, key=_task_sort_key)


def get_all_tasks() -> list[Task]:
    with db.get_db() as conn:
        tasks = _fetch_tasks(conn, "steward = 0")
    return sorted(tasks, key=_task_sort_key)


def get_subtasks(parent_id: str) -> list[Task]:
    with db.get_db() as conn:
        return _fetch_tasks(conn, "parent_id = ?", (parent_id,))


_TRACKED_FIELDS = {
    "content",
    "scheduled_date",
    "scheduled_time",
    "is_deadline",
    "focus",
    "completed_at",
}


def _record_mutation(conn: sqlite3.Connection, task_id: str, field: str, old_val, new_val) -> None:
    if field not in _TRACKED_FIELDS:
        return
    old_str = str(old_val) if old_val is not None else None
    new_str = str(new_val) if new_val is not None else None
    if old_str == new_str:
        return
    conn.execute(
        "INSERT INTO task_mutations (task_id, field, old_value, new_value) VALUES (?, ?, ?, ?)",
        (task_id, field, old_str, new_str),
    )


def _record_mutations(
    conn: sqlite3.Connection, task_id: str, old: Task, updates: dict[str, str]
) -> None:
    for field, new_val in updates.items():
        _record_mutation(conn, task_id, field, getattr(old, field, None), new_val)


UNSET: object = object()


def update_task(
    task_id: str,
    content: str | None = None,
    focus: bool | None = None,
    scheduled_date: str | object = UNSET,
    scheduled_time: str | object = UNSET,
    is_deadline: bool | object = UNSET,
    parent_id: str | object = UNSET,
    description: str | object = UNSET,
) -> Task | None:
    updates = {}
    if content is not None:
        updates["content"] = content
    if focus is not None:
        updates["focus"] = focus
    if scheduled_date is not UNSET:
        updates["scheduled_date"] = scheduled_date
    if scheduled_time is not UNSET:
        updates["scheduled_time"] = scheduled_time
    if is_deadline is not UNSET:
        updates["is_deadline"] = is_deadline
    if parent_id is not UNSET:
        updates["parent_id"] = parent_id
    if description is not UNSET:
        updates["description"] = description

    if updates:
        old = get_task(task_id)
        set_clauses = [f"{k} = ?" for k in updates]
        values = list(updates.values())
        values.append(task_id)

        with db.get_db() as conn:
            try:
                conn.execute(
                    f"UPDATE tasks SET {', '.join(set_clauses)} WHERE id = ?",  # noqa: S608
                    tuple(values),
                )
                if old:
                    _record_mutations(conn, task_id, old, updates)
            except sqlite3.IntegrityError as e:
                raise ValueError(f"Failed to update task: {e}") from e

    return get_task(task_id)


def get_mutations(task_id: str) -> list[TaskMutation]:
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT id, task_id, field, old_value, new_value, mutated_at, reason FROM task_mutations WHERE task_id = ? ORDER BY mutated_at DESC",
            (task_id,),
        ).fetchall()

    return [
        TaskMutation(
            id=r[0],
            task_id=r[1],
            field=r[2],
            old_value=r[3],
            new_value=r[4],
            mutated_at=datetime.fromisoformat(r[5]),
            reason=r[6],
        )
        for r in rows
    ]


def defer_task(task_id: str, reason: str) -> Task | None:
    task = get_task(task_id)
    if not task:
        return None
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO task_mutations (task_id, field, old_value, new_value, reason) VALUES (?, 'defer', NULL, NULL, ?)",
            (task_id, reason),
        )
    return task


def delete_task(task_id: str, cancel_reason: str | None = None) -> None:
    with db.get_db() as conn:
        row = conn.execute("SELECT id, content FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row:
            tag_rows = conn.execute("SELECT tag FROM tags WHERE task_id = ?", (task_id,)).fetchall()
            tags_str = ",".join(r[0] for r in tag_rows) if tag_rows else None
            if cancel_reason:
                conn.execute(
                    "INSERT INTO deleted_tasks (task_id, content, tags, cancel_reason, cancelled) VALUES (?, ?, ?, ?, 1)",
                    (row[0], row[1], tags_str, cancel_reason),
                )
            else:
                conn.execute(
                    "INSERT INTO deleted_tasks (task_id, content, tags) VALUES (?, ?, ?)",
                    (row[0], row[1], tags_str),
                )
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))


def cancel_task(task_id: str, reason: str) -> None:
    delete_task(task_id, cancel_reason=reason)


def check_task(task_id: str) -> tuple[Task | None, Task | None]:
    task = get_task(task_id)
    if not task or task.completed_at:
        return task, None
    completed = clock.now().strftime("%Y-%m-%dT%H:%M:%S")
    with db.get_db() as conn:
        conn.execute(
            "UPDATE tasks SET completed_at = ? WHERE id = ?",
            (completed, task_id),
        )
        _record_mutation(conn, task_id, "completed_at", None, completed)
        conn.execute(
            "UPDATE tasks SET blocked_by = NULL WHERE blocked_by = ?",
            (task_id,),
        )
    completed_task = get_task(task_id)
    parent_completed = None
    if task.parent_id:
        siblings = get_subtasks(task.parent_id)
        if all(s.completed_at for s in siblings):
            parent = get_task(task.parent_id)
            if parent and not parent.completed_at:
                with db.get_db() as conn:
                    conn.execute(
                        "UPDATE tasks SET completed_at = ? WHERE id = ?",
                        (completed, task.parent_id),
                    )
                    _record_mutation(conn, task.parent_id, "completed_at", None, completed)
                parent_completed = get_task(task.parent_id)
    return completed_task, parent_completed


def uncheck_task(task_id: str) -> Task | None:
    task = get_task(task_id)
    if not task or not task.completed_at:
        return task
    with db.get_db() as conn:
        conn.execute("UPDATE tasks SET completed_at = NULL WHERE id = ?", (task_id,))
        _record_mutation(conn, task_id, "completed_at", task.completed_at, None)
    if task.parent_id:
        parent = get_task(task.parent_id)
        if parent and parent.completed_at:
            with db.get_db() as conn:
                conn.execute("UPDATE tasks SET completed_at = NULL WHERE id = ?", (task.parent_id,))
                _record_mutation(conn, task.parent_id, "completed_at", parent.completed_at, None)
    return get_task(task_id)


def toggle_focus(task_id: str) -> Task | None:
    task = get_task(task_id)
    if not task:
        return None
    return update_task(task_id, focus=not task.focus)


def find_task(ref: str) -> Task | None:
    from .dashboard import _get_completed_today

    pending = get_tasks(include_steward=True)
    completed_today = _get_completed_today()
    return find_in_pool(ref, pending + completed_today)


def find_task_any(ref: str) -> Task | None:
    return find_in_pool(ref, get_all_tasks())


def find_task_exact(ref: str) -> Task | None:
    from .dashboard import _get_completed_today

    pending = get_tasks(include_steward=True)
    completed_today = _get_completed_today()
    return find_in_pool_exact(ref, pending + completed_today)


def set_blocked_by(task_id: str, blocker_id: str | None) -> Task | None:
    with db.get_db() as conn:
        conn.execute(
            "UPDATE tasks SET blocked_by = ? WHERE id = ?",
            (blocker_id, task_id),
        )
    return get_task(task_id)


def last_completion() -> datetime | None:
    with db.get_db() as conn:
        task_row = conn.execute(
            "SELECT completed_at FROM tasks WHERE completed_at IS NOT NULL ORDER BY completed_at DESC LIMIT 1"
        ).fetchone()
        check_row = conn.execute(
            "SELECT completed_at FROM habit_checks ORDER BY completed_at DESC LIMIT 1"
        ).fetchone()
    candidates: list[datetime] = []
    for row in (task_row, check_row):
        if row and row[0]:
            with contextlib.suppress(ValueError):
                candidates.append(datetime.fromisoformat(row[0]))
    return max(candidates) if candidates else None


def rename_task(task: Task, to_content: str) -> None:
    if task.content == to_content:
        exit_error(f"Error: Cannot rename '{task.content}' to itself.")
    update_task(task.id, content=to_content)
    print(f"→ {to_content}")


def check_task_cmd(task: Task) -> None:
    if task.completed_at:
        exit_error(f"'{task.content}' is already done")
    _, parent_completed = check_task(task.id)
    animate_check(task.content.lower())
    if parent_completed:
        animate_check(parent_completed.content.lower())


def _fmt_date_label(date_str: str) -> str:
    d = _date.fromisoformat(date_str)
    delta = (d - clock.today()).days
    if delta == 0:
        return "today"
    if delta == 1:
        return "tomorrow"
    return f"{d.day:02d}/{d.month:02d}"


def _schedule(args: list[str], remove: bool = False) -> None:
    from .lib.resolve import resolve_task

    if remove:
        if not args:
            exit_error("Usage: life schedule --remove <task>")
        try:
            _, _, item_name = parse_due_and_item(list(args), remove=True)
        except ValueError as e:
            exit_error(str(e))
        t = resolve_task(item_name)
        update_task(t.id, scheduled_date=None, scheduled_time=None, is_deadline=False)
        print(format_status("\u25a1", t.content, t.id))
        return
    try:
        date_str, time_str, item_name = parse_due_and_item(list(args))
    except ValueError as e:
        exit_error(str(e))
    if not date_str and not time_str:
        exit_error("Schedule spec required: today, tomorrow, day name, YYYY-MM-DD, HH:MM, or 'now'")
    t = resolve_task(item_name)
    updates: dict[str, Any] = {"is_deadline": False}
    if date_str:
        updates["scheduled_date"] = date_str
    if time_str:
        updates["scheduled_time"] = time_str
    update_task(t.id, **updates)
    if time_str:
        label = f"{ANSI.GREY}{time_str}{ANSI.RESET}"
    else:
        label = f"{ANSI.GREY}{_fmt_date_label(date_str or '')}{ANSI.RESET}"
    print(format_status(label, t.content, t.id))


# ── cli ──────────────────────────────────────────────────────────────────────


@cli("life")
def focus(ref: list[str]) -> None:
    """Pin task"""
    from .lib.resolve import resolve_task

    item_ref = " ".join(ref) if ref else ""
    if not item_ref:
        exit_error("Usage: life focus <item>")
    t = resolve_task(item_ref)
    toggle_focus(t.id)
    symbol = f"{ANSI.BOLD}\u29bf{ANSI.RESET}" if not t.focus else "\u25a1"
    print(format_status(symbol, t.content, t.id))


@cli("life")
def due(ref: list[str], when: str, remove: bool = False) -> None:
    """Mark task deadline"""
    from .lib.resolve import resolve_task

    args = ref if remove else [when, *ref]
    try:
        date_str, time_str, item_name = parse_due_and_item(args, remove=remove)
    except ValueError as e:
        exit_error(str(e))
    t = resolve_task(item_name)
    if remove:
        update_task(t.id, scheduled_date=None, scheduled_time=None, is_deadline=False)
        print(format_status("\u25a1", t.content, t.id))
        return
    if not date_str and not time_str:
        exit_error(
            "Due spec required: today, tomorrow, day name, YYYY-MM-DD, HH:MM, 'now', or -r to clear"
        )
    updates: dict[str, Any] = {"is_deadline": True}
    if date_str:
        updates["scheduled_date"] = date_str
    if time_str:
        updates["scheduled_time"] = time_str
    update_task(t.id, **updates)
    if time_str:
        label = f"{ANSI.CORAL}{time_str}{ANSI.RESET}"
    else:
        label = f"{ANSI.CORAL}{_fmt_date_label(date_str or '')}{ANSI.RESET}"
    print(format_status(label, t.content, t.id))


@cli("life", name="set")
def set_cmd(
    ref: list[str],
    parent: str | None = None,
    content: str | None = None,
    desc: str | None = None,
) -> None:
    """Set parent, content, or description on task"""
    from .lib.resolve import resolve_task

    item_ref = " ".join(ref) if ref else ""
    if not item_ref:
        exit_error("Usage: life set <task> [-p parent] [-c content]")
    t = resolve_task(item_ref)
    parent_id: str | None = None
    has_update = False
    if parent is not None:
        parent_task = resolve_task(parent)
        if parent_task.parent_id:
            exit_error("Error: subtasks cannot have subtasks")
        if parent_task.id == t.id:
            exit_error("Error: a task cannot be its own parent")
        if t.focus:
            exit_error("Error: cannot parent a focused task — unfocus first")
        parent_id = parent_task.id
        has_update = True
    if content is not None:
        if not content.strip():
            exit_error("Error: content cannot be empty")
        has_update = True
    description: str | None = None
    if desc is not None:
        description = desc if desc != "" else None
        has_update = True
    if not has_update:
        exit_error("Nothing to set. Use -p for parent, -c for content, or -d for description.")
    update_task(
        t.id,
        content=content,
        parent_id=parent_id if parent is not None else UNSET,
        description=description if desc is not None else UNSET,
    )
    updated = resolve_task(content or item_ref)
    prefix = "  \u2514 " if updated.parent_id else ""
    print(f"{prefix}{format_status('\u25a1', updated.content, updated.id)}")


@cli("life")
def show(ref: list[str]) -> None:
    """Show full task detail"""
    from .lib.render import render_task_detail
    from .lib.resolve import resolve_task

    item_ref = " ".join(ref) if ref else ""
    if not item_ref:
        exit_error("Usage: life show <task>")
    t = resolve_task(item_ref)
    if t.parent_id:
        parent = get_task(t.parent_id)
        parent_subtasks = get_subtasks(t.parent_id) if parent else []
        mutations = get_mutations(t.parent_id) if parent else []
        print(render_task_detail(t, [], mutations, parent=parent, parent_subtasks=parent_subtasks))
    else:
        subtasks = get_subtasks(t.id)
        mutations = get_mutations(t.id)
        print(render_task_detail(t, subtasks, mutations))


@cli("life")
def block(ref: list[str], by: str) -> None:
    """Mark task as blocked"""
    from .lib.resolve import resolve_task

    t = resolve_task(" ".join(ref))
    blocker = resolve_task(by)
    if blocker.id == t.id:
        exit_error("A task cannot block itself")
    set_blocked_by(t.id, blocker.id)
    print(f"\u2298 {t.content.lower()}  \u2190  {blocker.content.lower()}")


@cli("life")
def unblock(ref: list[str]) -> None:
    """Clear task block"""
    from .lib.resolve import resolve_task

    t = resolve_task(" ".join(ref))
    if not t.blocked_by:
        exit_error(f"'{t.content}' is not blocked")
    set_blocked_by(t.id, None)
    print(f"\u25a1 {t.content.lower()}  unblocked")


@cli("life")
def cancel(ref: list[str], reason: str) -> None:
    """Cancel task with reason"""
    from .lib.resolve import resolve_task

    t = resolve_task(" ".join(ref))
    cancel_task(t.id, reason)
    print(f"\u2717 {t.content.lower()} \u2014 {reason}")


@cli("life")
def defer(ref: list[str], reason: str) -> None:
    """Defer task with reason"""
    from .lib.resolve import resolve_task

    t = resolve_task(" ".join(ref))
    defer_task(t.id, reason)
    print(f"\u2192 {t.content.lower()} deferred: {reason}")


@cli(
    "life",
    help={
        "ref": "[DATE] [TIME] <task>  e.g. '14:00 call jeff', 'tomorrow 14:00 call jeff', '2026-03-01 09:00 dentist'"
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
    from .lib.clock import today as _today
    from .lib.resolve import resolve_task

    if overdue:
        today_date = _today()
        tasks = [t for t in get_all_tasks() if t.scheduled_date and t.scheduled_date < today_date]
        if not tasks:
            print("No overdue tasks.")
            return
        for t in tasks:
            update_task(t.id, scheduled_date=None, scheduled_time=None, is_deadline=False)
            print(format_status("□", t.content, t.id))
        return

    if not ref:
        raise UsageError("Usage: life unschedule <task> [task...]  or  --overdue")

    for r in ref:
        t = resolve_task(r)
        update_task(t.id, scheduled_date=None, scheduled_time=None, is_deadline=False)
        print(format_status("□", t.content, t.id))


@cli("life")
def today(ref: list[str]) -> None:
    """Schedule task for today"""
    _schedule(["today", *ref])

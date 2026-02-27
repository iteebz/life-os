import contextlib
import dataclasses
import sqlite3
import uuid
from datetime import date, datetime

from fncli import UsageError, cli

from . import db
from .core.errors import ValidationError
from .lib import ansi, clock
from .lib.converters import row_to_habit
from .lib.format import animate_check
from .lib.fuzzy import find_in_pool, find_in_pool_exact
from .models import Habit
from .tag import get_tags_for_habit, load_tags_for_habits

__all__ = [
    "add_habit",
    "archive_habit",
    "check_habit",
    "check_habit_cmd",
    "delete_habit",
    "find_habit",
    "get_archived_habits",
    "get_checks",
    "get_habit",
    "get_habits",
    "get_streak",
    "get_subhabits",
    "rename_habit",
    "toggle_check",
    "uncheck_habit",
    "update_habit",
]


# ── domain ───────────────────────────────────────────────────────────────────


_HABIT_COLS = "id, content, created, archived_at, parent_id, private"


def _hydrate_habit(habit: Habit, checks: list[datetime], tags: list[str]) -> Habit:
    return dataclasses.replace(habit, checks=checks, tags=tags)


def _get_habit_checks(conn, habit_id: str) -> list[datetime]:
    cursor = conn.execute(
        "SELECT completed_at FROM habit_checks WHERE habit_id = ? ORDER BY completed_at",
        (habit_id,),
    )
    return [datetime.fromisoformat(row[0]) for row in cursor.fetchall()]


def _fetch_habits(
    conn: sqlite3.Connection, where: str, params: tuple[object, ...] = ()
) -> list[Habit]:
    """Fetch habits matching a WHERE clause and hydrate checks + tags."""
    cursor = conn.execute(
        f"SELECT {_HABIT_COLS} FROM habits WHERE {where}",  # noqa: S608
        params,
    )
    rows = cursor.fetchall()
    all_ids = [row[0] for row in rows]
    tags_map = load_tags_for_habits(all_ids, conn=conn)
    return [
        _hydrate_habit(row_to_habit(row), _get_habit_checks(conn, row[0]), tags_map.get(row[0], []))
        for row in rows
    ]


def add_habit(
    content: str,
    tags: list[str] | None = None,
    parent_id: str | None = None,
    private: bool = False,
) -> str:
    habit_id = str(uuid.uuid4())
    with db.get_db() as conn:
        try:
            conn.execute(
                "INSERT INTO habits (id, content, parent_id, private) VALUES (?, ?, ?, ?)",
                (habit_id, content, parent_id, int(private)),
            )
        except sqlite3.IntegrityError as e:
            raise ValueError(f"Failed to add habit: {e}") from e

        if tags:
            for tag in tags:
                with contextlib.suppress(sqlite3.IntegrityError):
                    conn.execute(
                        "INSERT INTO tags (habit_id, tag) VALUES (?, ?)",
                        (habit_id, tag.lower()),
                    )
    return habit_id


def get_habit(habit_id: str) -> Habit | None:
    with db.get_db() as conn:
        cursor = conn.execute(
            "SELECT id, content, created, archived_at, parent_id, private FROM habits WHERE id = ?",
            (habit_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        habit = row_to_habit(row)
        checks = _get_habit_checks(conn, habit_id)
        tags = get_tags_for_habit(habit_id)
        return _hydrate_habit(habit, checks, tags)


def update_habit(habit_id: str, content: str | None = None) -> Habit | None:
    if content is None:
        return get_habit(habit_id)

    with db.get_db() as conn:
        try:
            conn.execute(
                "UPDATE habits SET content = ? WHERE id = ?",
                (content, habit_id),
            )
        except sqlite3.IntegrityError as e:
            raise ValueError(f"Failed to update habit: {e}") from e

    return get_habit(habit_id)


def delete_habit(habit_id: str) -> None:
    with db.get_db() as conn:
        conn.execute("DELETE FROM habits WHERE id = ?", (habit_id,))


def get_habits(habit_ids: list[str] | None = None, include_private: bool = True) -> list[Habit]:
    if habit_ids is None:
        private_filter = "" if include_private else " AND private = 0"
        where = f"archived_at IS NULL{private_filter}"
        with db.get_db() as conn:
            return _fetch_habits(conn, f"{where} ORDER BY created DESC")

    if not habit_ids:
        return []
    placeholders = ",".join("?" * len(habit_ids))
    with db.get_db() as conn:
        return _fetch_habits(conn, f"id IN ({placeholders})", tuple(habit_ids))


def get_checks(habit_id: str) -> list[datetime]:
    if not habit_id:
        raise ValueError("habit_id cannot be empty")

    with db.get_db() as conn:
        cursor = conn.execute(
            "SELECT completed_at FROM habit_checks WHERE habit_id = ? ORDER BY completed_at DESC",
            (habit_id,),
        )
        return [datetime.fromisoformat(row[0]) for row in cursor.fetchall()]


def get_streak(habit_id: str) -> int:
    if not habit_id:
        raise ValueError("habit_id cannot be empty")

    checks = get_checks(habit_id)

    if not checks:
        return 0

    streak = 1
    today = clock.today()

    for i in range(len(checks) - 1):
        current = checks[i].date()
        next_date = checks[i + 1].date()
        if (current - next_date).days == 1:
            streak += 1
        else:
            break

    if checks[0].date() != today:
        return 0

    return streak


def get_subhabits(parent_id: str) -> list["Habit"]:
    with db.get_db() as conn:
        return _fetch_habits(
            conn, "parent_id = ? AND archived_at IS NULL ORDER BY created ASC", (parent_id,)
        )


def get_archived_habits() -> list[Habit]:
    with db.get_db() as conn:
        return _fetch_habits(conn, "archived_at IS NOT NULL ORDER BY archived_at DESC")


def archive_habit(habit_id: str) -> Habit | None:
    habit = get_habit(habit_id)
    if not habit:
        return None
    archived_at = datetime.now().isoformat()
    with db.get_db() as conn:
        conn.execute(
            "UPDATE habits SET archived_at = ? WHERE id = ?",
            (archived_at, habit_id),
        )
    return get_habit(habit_id)


def find_habit(ref: str) -> Habit | None:
    return find_in_pool(ref, get_habits())


def find_habit_exact(ref: str) -> Habit | None:
    return find_in_pool_exact(ref, get_habits())


def check_habit(habit_id: str, check_on: date | None = None) -> Habit | None:
    habit = get_habit(habit_id)
    if not habit:
        return None
    if check_on is not None:
        check_date = check_on.isoformat()
        completed_at = f"{check_date}T23:59:59"
    else:
        check_date = clock.today().isoformat()
        completed_at = datetime.now().isoformat()
    with db.get_db() as conn:
        with contextlib.suppress(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO habit_checks (habit_id, check_date, completed_at) VALUES (?, ?, ?)",
                (habit_id, check_date, completed_at),
            )
    return get_habit(habit_id)


def uncheck_habit(habit_id: str, check_on: date | None = None) -> Habit | None:
    habit = get_habit(habit_id)
    if not habit:
        return None
    check_date = check_on.isoformat() if check_on is not None else clock.today().isoformat()
    with db.get_db() as conn:
        conn.execute(
            "DELETE FROM habit_checks WHERE habit_id = ? AND check_date = ?",
            (habit_id, check_date),
        )
    return get_habit(habit_id)


def toggle_check(habit_id: str) -> Habit | None:
    habit = get_habit(habit_id)
    if not habit:
        return None
    with db.get_db() as conn:
        cursor = conn.execute(
            "SELECT 1 FROM habit_checks WHERE habit_id = ? AND check_date = ?",
            (habit_id, clock.today().isoformat()),
        )
        if cursor.fetchone():
            return uncheck_habit(habit_id)
    return check_habit(habit_id)


def rename_habit(habit: Habit, to_content: str) -> None:
    if habit.content == to_content:
        raise ValidationError(f"cannot rename '{habit.content}' to itself")
    update_habit(habit.id, content=to_content)
    print(f"\u2192 {to_content}")


def check_habit_cmd(habit: Habit) -> None:
    from .lib.clock import today

    updated = toggle_check(habit.id)
    if updated:
        checked_today = any(c.date() == today() for c in updated.checks)
        if checked_today:
            animate_check(habit.content.lower())


# ── cli ──────────────────────────────────────────────────────────────────────


@cli("life")
def archive(ref: str | None = None, list_archived: bool = False) -> None:
    """Archive habit"""
    from .lib.resolve import resolve_habit

    if list_archived:
        archived_habits = get_archived_habits()
        if not archived_habits:
            print("no archived habits")
            return
        for h in archived_habits:
            archived_date = h.archived_at.strftime("%Y-%m-%d") if h.archived_at else "?"
            print(f"{ansi.dim(h.content)}  archived {archived_date}")
        return
    if not ref:
        raise UsageError("Usage: life archive <habit>")
    h = resolve_habit(ref)
    archive_habit(h.id)
    print(f"{ansi.dim(h.content)}  archived")


@cli("life")
def habits() -> None:
    """Show habits matrix"""
    from .lib.render import render_habit_matrix

    print(render_habit_matrix(get_habits()))

import contextlib
import dataclasses
import sqlite3
import uuid
from datetime import date, datetime, timedelta

from fncli import UsageError, cli

from .core.errors import ValidationError
from .core.models import Habit
from .lib import ansi, clock
from .lib.converters import row_to_habit
from .lib.format import render_done_row
from .lib.fuzzy import find_in_pool, find_in_pool_exact
from .lib.store import get_db
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


_HABIT_COLS = "id, content, created, archived_at, parent_id, private, cadence"


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
    cadence: str = "daily",
) -> str:
    habit_id = str(uuid.uuid4())
    with get_db() as conn:
        try:
            conn.execute(
                "INSERT INTO habits (id, content, parent_id, private, cadence)"
                " VALUES (?, ?, ?, ?, ?)",
                (habit_id, content, parent_id, int(private), cadence),
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
    with get_db() as conn:
        cursor = conn.execute(
            f"SELECT {_HABIT_COLS} FROM habits WHERE id = ? AND deleted_at IS NULL",  # noqa: S608
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

    with get_db() as conn:
        try:
            conn.execute(
                "UPDATE habits SET content = ? WHERE id = ?",
                (content, habit_id),
            )
        except sqlite3.IntegrityError as e:
            raise ValueError(f"Failed to update habit: {e}") from e

    return get_habit(habit_id)


def delete_habit(habit_id: str) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE habits SET deleted_at = STRFTIME('%Y-%m-%dT%H:%M:%S', 'now') WHERE id = ?",
            (habit_id,),
        )


def get_habits(habit_ids: list[str] | None = None, include_private: bool = True) -> list[Habit]:
    if habit_ids is None:
        private_filter = "" if include_private else " AND private = 0"
        where = f"deleted_at IS NULL AND archived_at IS NULL{private_filter}"
        with get_db() as conn:
            return _fetch_habits(conn, f"{where} ORDER BY created DESC")

    if not habit_ids:
        return []
    placeholders = ",".join("?" * len(habit_ids))
    with get_db() as conn:
        return _fetch_habits(
            conn, f"deleted_at IS NULL AND id IN ({placeholders})", tuple(habit_ids)
        )


def get_checks(habit_id: str) -> list[datetime]:
    if not habit_id:
        raise ValueError("habit_id cannot be empty")

    with get_db() as conn:
        cursor = conn.execute(
            "SELECT completed_at FROM habit_checks WHERE habit_id = ? ORDER BY completed_at DESC",
            (habit_id,),
        )
        return [datetime.fromisoformat(row[0]) for row in cursor.fetchall()]


def get_streak(habit_id: str) -> int:
    if not habit_id:
        raise ValueError("habit_id cannot be empty")

    habit = get_habit(habit_id)
    if not habit:
        return 0

    checks = get_checks(habit_id)
    if not checks:
        return 0

    today = clock.today()

    if habit.cadence == "weekly":
        check_dates = sorted({c.date() for c in checks}, reverse=True)
        # Convert dates to Monday-based week start for reliable comparison
        week_starts = sorted(
            {d - timedelta(days=d.weekday()) for d in check_dates},
            reverse=True,
        )
        if not week_starts:
            return 0
        current_week_start = today - timedelta(days=today.weekday())
        # Allow current or previous week to count as "active"
        if week_starts[0] not in (
            current_week_start,
            current_week_start - timedelta(weeks=1),
        ):
            return 0
        streak = 1
        for i in range(len(week_starts) - 1):
            gap = (week_starts[i] - week_starts[i + 1]).days
            if gap == 7:
                streak += 1
            else:
                break
        return streak

    streak = 1
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
    with get_db() as conn:
        return _fetch_habits(
            conn,
            "parent_id = ? AND deleted_at IS NULL AND archived_at IS NULL ORDER BY created ASC",
            (parent_id,),
        )


def get_archived_habits() -> list[Habit]:
    with get_db() as conn:
        return _fetch_habits(
            conn, "deleted_at IS NULL AND archived_at IS NOT NULL ORDER BY archived_at DESC"
        )


def archive_habit(habit_id: str) -> Habit | None:
    habit = get_habit(habit_id)
    if not habit:
        return None
    archived_at = datetime.now().isoformat()
    with get_db() as conn:
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
    with get_db() as conn:
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
    with get_db() as conn:
        conn.execute(
            "DELETE FROM habit_checks WHERE habit_id = ? AND check_date = ?",
            (habit_id, check_date),
        )
    return get_habit(habit_id)


def toggle_check(habit_id: str) -> Habit | None:
    habit = get_habit(habit_id)
    if not habit:
        return None
    with get_db() as conn:
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


def check_habit_cmd(habit: Habit) -> None:
    from .lib.clock import today

    updated = toggle_check(habit.id)
    if updated:
        today_date = today()
        checked_today = any(c.date() == today_date for c in updated.checks)
        if checked_today:
            today_checks = [c for c in updated.checks if c.date() == today_date]
            time_str = max(today_checks).strftime("%H:%M") if today_checks else ""
            render_done_row(habit.content.lower(), time_str, habit.tags, habit.id, is_habit=True)


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


def _render_habit_matrix(habits: list[Habit]) -> str:
    if not habits:
        return "No habits found."
    today = clock.today()
    daily = [h for h in habits if h.cadence == "daily"]
    weekly = [h for h in habits if h.cadence == "weekly"]
    muted = ansi.theme.muted
    reset = ansi.theme.reset
    lines: list[str] = []

    if daily:
        lines.append("HABIT TRACKER (last 7 days)\n")
        day_names = [(today - timedelta(days=i)).strftime("%a").lower() for i in range(6, -1, -1)]
        dates = [(today - timedelta(days=i)) for i in range(6, -1, -1)]
        header = "habit           " + " ".join(day_names) + "   key"
        lines += [header, "-" * len(header)]
        for h in sorted(daily, key=lambda h: h.content.lower()):
            check_dates = {dt.date() for dt in h.checks}
            indicators = ["●" if d in check_dates else "○" for d in dates]
            cells = "   ".join(indicators)
            lines.append(f"{h.content.lower():<15} {cells}   {muted}[{h.id[:8]}]{reset}")

    if weekly:
        if daily:
            lines.append("")
        lines.append("WEEKLY (last 4 weeks)\n")
        week_ranges: list[tuple[date, date]] = []
        for i in range(3, -1, -1):
            end = today - timedelta(days=today.weekday()) - timedelta(weeks=i) + timedelta(days=6)
            start = end - timedelta(days=6)
            if i == 0:
                end = today
                start = today - timedelta(days=today.weekday())
            week_ranges.append((start, end))
        week_labels = [f"w{i + 1}" for i in range(4)]
        header = "habit           " + "  ".join(f"{w:>3}" for w in week_labels) + "   key"
        lines += [header, "-" * len(header)]
        for h in sorted(weekly, key=lambda h: h.content.lower()):
            check_dates = {dt.date() for dt in h.checks}
            indicators = []
            for start, end in week_ranges:
                hit = any(start <= d <= end for d in check_dates)
                indicators.append(" ● " if hit else " ○ ")
            cells = "  ".join(indicators)
            lines.append(f"{h.content.lower():<15} {cells}   {muted}[{h.id[:8]}]{reset}")

    return "\n".join(lines)


@cli("life")
def habits() -> None:
    """Show habits matrix"""
    print(_render_habit_matrix(get_habits()))


@cli("life", flags={"ref": [], "tag": ["-t", "--tag"]})
def habit(ref: list[str] | None = None, tag: list[str] | None = None, weekly: bool = False) -> None:
    """List habits, or create one: `life habit "name" -t tag`"""
    if not ref:
        print(_render_habit_matrix(get_habits()))
        return
    name = " ".join(ref)
    cadence = "weekly" if weekly else "daily"
    add_habit(name, tags=tag, cadence=cadence)
    cadence_str = " (weekly)" if weekly else ""
    suffix = " " + " ".join(f"#{t}" for t in tag) if tag else ""
    print(f"→ {name}{suffix}{cadence_str}")

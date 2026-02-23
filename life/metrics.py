from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .db import get_db
from .models import Habit, Task

DISCOMFORT_TAGS = {"finance", "legal", "janice"}


@dataclass(frozen=True)
class FeedbackSnapshot:
    admin_closed: int
    admin_open: int
    janice_done: int
    janice_open: int
    defer_count: int
    habit_rate: float
    habit_checked: int
    habit_possible: int
    overdue_resets: int
    flags: list[str]


def _in_window(ts: datetime | None, start: date, end: date) -> bool:
    if ts is None:
        return False
    day = ts.date()
    return start <= day <= end


def _format_ratio(done: int, total: int) -> str:
    if total == 0:
        return "n/a"
    return f"{done / total:.0%}"


def _count_defers(window_start: date, window_end: date) -> int:
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM task_mutations WHERE field = 'defer' AND date(mutated_at) >= ? AND date(mutated_at) <= ?",
            (window_start.isoformat(), window_end.isoformat()),
        ).fetchone()
        return row[0] if row else 0


def _count_overdue_resets(window_start: date, window_end: date) -> int:
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM task_mutations WHERE reason = 'overdue_reset' AND date(mutated_at) >= ? AND date(mutated_at) <= ?",
            (window_start.isoformat(), window_end.isoformat()),
        ).fetchone()
        return row[0] if row else 0


def build_feedback_snapshot(
    *,
    all_tasks: list[Task],
    pending_tasks: list[Task],
    habits: list[Habit],
    today: date,
    window_days: int = 7,
) -> FeedbackSnapshot:
    window_start = today - timedelta(days=window_days - 1)

    admin_closed = sum(
        1
        for t in all_tasks
        if set(t.tags or []).intersection(DISCOMFORT_TAGS)
        and _in_window(t.completed_at, window_start, today)
    )
    admin_open = sum(1 for t in pending_tasks if set(t.tags or []).intersection(DISCOMFORT_TAGS))

    janice_done = sum(
        1
        for t in all_tasks
        if "janice" in (t.tags or []) and _in_window(t.completed_at, window_start, today)
    )
    janice_open = sum(1 for t in pending_tasks if "janice" in (t.tags or []))

    defer_count = _count_defers(window_start, today)
    overdue_resets = _count_overdue_resets(window_start, today)

    habit_possible = len(habits) * window_days
    habit_checked = sum(1 for h in habits for c in h.checks if window_start <= c.date() <= today)
    habit_rate = habit_checked / habit_possible if habit_possible else 0.0

    flags: list[str] = []
    janice_total = janice_done + janice_open
    if janice_total and (janice_done / janice_total) < 0.5:
        flags.append("relationship_escalation")
    if admin_open > 0 and admin_closed == 0:
        flags.append("admin_stalled")
    if defer_count >= 3:
        flags.append("avoidance_pattern")
    if habit_rate < 0.3:
        flags.append("habit_decay")

    return FeedbackSnapshot(
        admin_closed=admin_closed,
        admin_open=admin_open,
        janice_done=janice_done,
        janice_open=janice_open,
        defer_count=defer_count,
        habit_rate=habit_rate,
        habit_checked=habit_checked,
        habit_possible=habit_possible,
        overdue_resets=overdue_resets,
        flags=flags,
    )


def render_feedback_snapshot(snapshot: FeedbackSnapshot) -> list[str]:
    admin_total = snapshot.admin_closed + snapshot.admin_open
    janice_total = snapshot.janice_done + snapshot.janice_open
    lines = [
        "STATS (7d):",
        f"  admin_closure_rate: {_format_ratio(snapshot.admin_closed, admin_total)} ({snapshot.admin_closed}/{admin_total})",
        f"  janice_followthrough: {_format_ratio(snapshot.janice_done, janice_total)} ({snapshot.janice_done}/{janice_total})",
        f"  habit_rate: {snapshot.habit_rate:.0%} ({snapshot.habit_checked}/{snapshot.habit_possible})",
        f"  defers: {snapshot.defer_count}",
        f"  overdue_resets: {snapshot.overdue_resets}",
    ]
    if snapshot.flags:
        lines.append("  flags: " + ", ".join(snapshot.flags))
    else:
        lines.append("  flags: none")
    return lines


__all__ = [
    "FeedbackSnapshot",
    "build_feedback_snapshot",
    "render_feedback_snapshot",
]

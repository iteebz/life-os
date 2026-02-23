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


def _is_top_level(t: Task) -> bool:
    return t.parent_id is None


def build_feedback_snapshot(
    *,
    all_tasks: list[Task],
    pending_tasks: list[Task],
    habits: list[Habit],
    today: date,
    window_days: int = 7,
) -> FeedbackSnapshot:
    window_start = today - timedelta(days=window_days - 1)

    top_all = [t for t in all_tasks if _is_top_level(t)]
    top_pending = [t for t in pending_tasks if _is_top_level(t)]

    admin_closed = sum(
        1
        for t in top_all
        if set(t.tags or []).intersection(DISCOMFORT_TAGS)
        and _in_window(t.completed_at, window_start, today)
    )
    admin_open = sum(1 for t in top_pending if set(t.tags or []).intersection(DISCOMFORT_TAGS))

    janice_done = sum(
        1
        for t in top_all
        if "janice" in (t.tags or []) and _in_window(t.completed_at, window_start, today)
    )
    janice_open = sum(1 for t in top_pending if "janice" in (t.tags or []))

    defer_count = _count_defers(window_start, today)
    overdue_resets = _count_overdue_resets(window_start, today)

    habit_possible = len(habits) * window_days
    habit_checked = sum(1 for h in habits for c in h.checks if window_start <= c.date() <= today)
    habit_rate = habit_checked / habit_possible if habit_possible else 0.0

    flags: list[str] = []
    janice_total = janice_done + janice_open
    if janice_total and (janice_done / janice_total) < 0.5:
        flags.append("partner_at_risk")
    if admin_open > 0 and admin_closed == 0:
        flags.append("stuck")
    if defer_count >= 3:
        flags.append("dodging")
    if habit_rate < 0.3:
        flags.append("drifting")

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
        f"  closure:  {_format_ratio(snapshot.admin_closed, admin_total)} ({snapshot.admin_closed}/{admin_total})",
        f"  partner:  {_format_ratio(snapshot.janice_done, janice_total)} ({snapshot.janice_done}/{janice_total})",
        f"  rhythm:   {snapshot.habit_rate:.0%} ({snapshot.habit_checked}/{snapshot.habit_possible})",
        f"  dodges:   {snapshot.defer_count}",
        f"  slips:    {snapshot.overdue_resets}",
    ]
    if snapshot.flags:
        lines.append("  flags:  " + ", ".join(snapshot.flags))
    else:
        lines.append("  flags:  none")
    return lines


def render_feedback_headline(snapshot: FeedbackSnapshot) -> str:
    admin_total = snapshot.admin_closed + snapshot.admin_open
    janice_total = snapshot.janice_done + snapshot.janice_open
    parts = []
    if admin_total:
        parts.append(f"closure {_format_ratio(snapshot.admin_closed, admin_total)}")
    if janice_total:
        parts.append(f"partner {_format_ratio(snapshot.janice_done, janice_total)}")
    parts.append(f"rhythm {snapshot.habit_rate:.0%}")
    if snapshot.flags:
        parts.append("⚑ " + ", ".join(snapshot.flags))
    return "  ".join(parts)


__all__ = [
    "FeedbackSnapshot",
    "build_feedback_snapshot",
    "render_feedback_headline",
    "render_feedback_snapshot",
]

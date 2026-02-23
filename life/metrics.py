from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .db import get_db
from .models import Habit, Task

DISCOMFORT_TAGS = {"finance", "legal", "janice"}

TAG_WEIGHT: dict[str, int] = {
    "finance": 3,
    "legal": 3,
    "janice": 2,
    "health": 2,
    "eam": 2,
    "home": 1,
    "admin": 1,
    "comms": 1,
    "self": 1,
    "doggo": 1,
    "ncat": 2,
    "income": 2,
}
DEFAULT_WEIGHT = 1


@dataclass(frozen=True)
class FeedbackSnapshot:
    closure_score: float
    closure_earned: float
    closure_possible: float
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


def _task_weight(t: Task) -> int:
    tags = t.tags or []
    return max((TAG_WEIGHT.get(tag, DEFAULT_WEIGHT) for tag in tags), default=DEFAULT_WEIGHT)


def _format_pct(value: float) -> str:
    return f"{value:.0%}"


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

    closure_earned = sum(
        _task_weight(t) for t in top_all if _in_window(t.completed_at, window_start, today)
    )
    closure_open = sum(_task_weight(t) for t in top_pending)
    closure_possible = closure_earned + closure_open
    closure_score = closure_earned / closure_possible if closure_possible else 0.0

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
    if closure_possible > 0 and closure_score < 0.2:
        flags.append("stuck")
    if defer_count >= 3:
        flags.append("dodging")
    if habit_rate < 0.3:
        flags.append("drifting")

    return FeedbackSnapshot(
        closure_score=closure_score,
        closure_earned=closure_earned,
        closure_possible=closure_possible,
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
    janice_total = snapshot.janice_done + snapshot.janice_open
    lines = [
        "STATS (7d):",
        f"  closure:  {_format_pct(snapshot.closure_score)} ({snapshot.closure_earned:.0f}/{snapshot.closure_possible:.0f} pts)",
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
    janice_total = snapshot.janice_done + snapshot.janice_open
    parts = [f"closure {_format_pct(snapshot.closure_score)}"]
    if janice_total:
        parts.append(f"partner {_format_ratio(snapshot.janice_done, janice_total)}")
    parts.append(f"rhythm {snapshot.habit_rate:.0%}")
    if snapshot.flags:
        parts.append("⚑ " + ", ".join(snapshot.flags))
    return "  ".join(parts)


__all__ = [
    "TAG_WEIGHT",
    "FeedbackSnapshot",
    "build_feedback_snapshot",
    "render_feedback_headline",
    "render_feedback_snapshot",
]

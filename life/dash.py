from datetime import date, timedelta

from fncli import UsageError, cli

from .dashboard import (
    get_day_breakdown,
    get_day_completed,
    get_pending_items,
    get_today_breakdown,
    get_today_completed,
)
from .habits import get_habits
from .lib.clock import now, today
from .lib.render import render_dashboard, render_day_summary, render_momentum
from .metrics import build_feedback_snapshot, render_feedback_snapshot
from .momentum import weekly_momentum
from .tasks import get_all_tasks, get_tasks, last_completion

__all__ = [
    "dashboard",
    "momentum",
    "stats",
    "status",
    "view",
    "yesterday",
]


@cli("life")
def dashboard(verbose: bool = False) -> None:
    """Life dashboard"""
    items = get_pending_items() + get_habits()
    today_items = get_today_completed()
    today_breakdown = get_today_breakdown()
    print(render_dashboard(items, today_breakdown, None, None, today_items, verbose=verbose))


def _format_elapsed(dt) -> str:
    delta = now() - dt
    s = int(delta.total_seconds())
    if s < 60:
        return f"{s}s ago"
    m = s // 60
    if m < 60:
        return f"{m}m ago"
    h = m // 60
    if h < 24:
        return f"{h}h ago"
    d = h // 24
    return f"{d}d ago"


@cli("life")
def status() -> None:
    """Health check — untagged tasks, overdue, habit streaks, janice signal"""
    tasks = get_tasks()
    all_tasks = get_all_tasks()
    habits = get_habits()
    today_date = today()

    untagged = [t for t in tasks if not t.tags]
    overdue = [t for t in tasks if t.scheduled_date and t.scheduled_date < today_date]
    janice = [t for t in tasks if "janice" in (t.tags or [])]
    focused = [t for t in tasks if t.focus]

    snapshot = build_feedback_snapshot(
        all_tasks=all_tasks, pending_tasks=tasks, habits=habits, today=today_date
    )

    lc = last_completion()
    last_check_str = _format_elapsed(lc) if lc else "never"

    lines = []
    lines.append(
        f"tasks: {len(tasks)}  habits: {len(habits)}  focused: {len(focused)}  last check: {last_check_str}"
    )
    lines.append("\nHEALTH:")
    lines.append(f"  untagged: {len(untagged)}")
    lines.append(f"  overdue: {len(overdue)}")
    lines.append(f"  janice_open: {len(janice)}")
    lines.append("\nFLAGS:")
    if snapshot.flags:
        lines.append("  " + ", ".join(snapshot.flags))
    else:
        lines.append("  none")
    lines.append("\nHOT LIST:")
    overdue_ids = {t.id for t in overdue}
    hot_overdue = overdue[:3]
    hot_janice = [t for t in janice if t.id not in overdue_ids][:3]
    lines.extend(f"  ! {t.content}" for t in hot_overdue)
    lines.extend(f"  \u2665 {t.content}" for t in hot_janice)
    if not hot_overdue and not hot_janice:
        lines.append("  none")
    print("\n".join(lines))


@cli("life")
def stats() -> None:
    """Feedback-loop metrics and escalation signals"""
    tasks = get_tasks()
    all_tasks = get_all_tasks()
    habits = get_habits()
    today_date = today()
    snapshot = build_feedback_snapshot(
        all_tasks=all_tasks, pending_tasks=tasks, habits=habits, today=today_date
    )
    print("\n".join(render_feedback_snapshot(snapshot)))


@cli("life")
def yesterday() -> None:
    """Show yesterday's completed tasks and stats"""
    target = today() - timedelta(days=1)
    _show_day(target)


@cli("life")
def view(date_str: str) -> None:
    """Show completed tasks and stats for a given date (YYYY-MM-DD)"""
    try:
        target = date.fromisoformat(date_str)
    except ValueError:
        raise UsageError(f"invalid date: {date_str!r} — use YYYY-MM-DD") from None
    _show_day(target)


def _show_day(target: date) -> None:
    from .db import get_db

    date_str = target.isoformat()
    completed = get_day_completed(date_str)
    breakdown = get_day_breakdown(date_str)

    mood = None
    with get_db() as conn:
        row = conn.execute(
            "SELECT score, label FROM mood_log WHERE DATE(logged_at) = DATE(?) ORDER BY logged_at DESC LIMIT 1",
            (date_str,),
        ).fetchone()
        if row:
            mood = (row[0], row[1])

    print(render_day_summary(target, completed, breakdown, mood))


@cli("life")
def momentum() -> None:
    """Show momentum and weekly trends"""
    print(render_momentum(weekly_momentum()))

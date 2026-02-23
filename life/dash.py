from datetime import date, datetime, timedelta

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
    """System health check"""
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
    """Feedback-loop metrics"""
    tasks = get_tasks()
    all_tasks = get_all_tasks()
    habits = get_habits()
    today_date = today()
    snapshot = build_feedback_snapshot(
        all_tasks=all_tasks, pending_tasks=tasks, habits=habits, today=today_date
    )
    print("\n".join(render_feedback_snapshot(snapshot)))


@cli("life")
def view(date_str: str) -> None:
    """Show completed tasks for a date (yesterday, dd-mm, dd-mm-yyyy, yyyy-mm-dd)"""
    from .lib.clock import today as _today

    if date_str.lower() == "yesterday":
        _show_day(_today() - timedelta(days=1))
        return
    if date_str.lower() == "today":
        _show_day(_today())
        return
    target = None
    for fmt in ("%d-%m-%Y", "%d-%m", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(date_str, fmt)
            if fmt == "%d-%m":
                parsed = parsed.replace(year=_today().year)
            target = parsed.date()
            break
        except ValueError:
            continue
    if target is None:
        raise UsageError(
            f"invalid date: {date_str!r} — use yesterday, today, dd-mm, dd-mm-yyyy, or yyyy-mm-dd"
        ) from None
    _show_day(target)


def _show_day(target: date) -> None:
    from .db import get_db
    from .habits import get_habits

    date_str = target.isoformat()
    completed = get_day_completed(date_str)
    breakdown = get_day_breakdown(date_str)
    total_habits = len([h for h in get_habits() if not h.parent_id and not h.private])

    mood = None
    with get_db() as conn:
        row = conn.execute(
            "SELECT score, label FROM mood_log WHERE DATE(logged_at) = DATE(?) ORDER BY logged_at DESC LIMIT 1",
            (date_str,),
        ).fetchone()
        if row:
            mood = (row[0], row[1])

    print(render_day_summary(target, completed, breakdown, mood, total_habits))


@cli("life")
def momentum() -> None:
    """Momentum and weekly trends"""
    print(render_momentum(weekly_momentum()))

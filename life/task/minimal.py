"""Minimal dashboard — done timeline, habits scannable, today+tomorrow tasks."""

from datetime import date, timedelta

from life.task.rows import RenderCtx, habit_sort_key, row_daily_habit, row_task
from life.task.sections import section_header, section_overdue, section_schedule, section_vices
from lifeos.core.lib import clock
from lifeos.core.lib.ansi import bold, gold, gray, purple, theme
from lifeos.core.lib.dates import upcoming_dates
from lifeos.core.lib.format import fmt_time
from lifeos.core.models import Habit, Task

_R = theme.reset


def _pad_hm(t: str) -> str:
    if ":" in t and len(t.split(":", 1)[0]) == 1:
        return "0" + t
    return t


def _habits(all_habits: list[Habit], checked_ids: set[str], ctx: RenderCtx) -> list[str]:
    habits = [
        h
        for h in all_habits
        if not h.private and not h.parent_id and "vice" not in (h.tags or []) and h.cadence != "weekly"
    ]
    if not habits:
        return []
    pending = [h for h in habits if h.id not in checked_ids]
    done_count = len(habits) - len(pending)
    lines = [f"\n{bold(purple(f'HABITS ({done_count}/{len(habits)})'))}"]
    for habit in sorted(pending, key=habit_sort_key):
        lines.extend(row_daily_habit(habit, checked_ids, ctx))
    return lines


def _today(ctx: RenderCtx, today_str: str, events: list[dict[str, object]]) -> list[str]:
    now_dt = clock.now()
    now_time = now_dt.strftime("%H:%M")
    now_display = fmt_time(now_dt)

    due_today = [t for t in ctx.pending if t.scheduled_date and t.scheduled_date.isoformat() == today_str]

    rows: list[tuple[str, list[str]]] = []
    for task in due_today:
        t_str = _pad_hm(task.scheduled_time) if task.scheduled_time else "zz:zz"
        rows.append((t_str, row_task(task, ctx, {}, show_date=False, show_parent=True)))

    event_emoji = {"birthday": "🎂", "anniversary": "💍", "deadline": "⚠️", "other": "📌"}
    for ev in events:
        emoji = event_emoji.get(str(ev.get("type", "")), "📌")
        rows.append(("zz:zz", [f"  {emoji} {str(ev.get('name', '')).lower()}"]))

    rows.sort(key=lambda x: x[0])

    count = len(due_today) + len(events)
    lines = [f"\n{bold(gold(f'TODAY ({count})'))}"]
    now_marker = f"  {gray('─')} {theme.coral}▸ {now_display}{gray(' ──────────────')}{_R}"

    now_inserted = False
    for t_str, row_lines in rows:
        if not now_inserted and (t_str == "zz:zz" or t_str > now_time):
            lines.append(now_marker)
            now_inserted = True
        lines.extend(row_lines)
    if not now_inserted:
        lines.append(now_marker)
    if count == 0:
        lines.append(f"  {gray('nothing scheduled.')}")
    return lines


def render_minimal(
    items: list[Task | Habit],
    today_breakdown: tuple[int, int, int, int],
    today_items: list[Task | Habit] | None = None,
) -> str:
    """Three blocks: DONE timeline, HABITS scannable, TASKS today+tomorrow."""
    from life.task.render import _section_done_today

    habits_today, tasks_today, added_today, deleted_today = today_breakdown
    ctx = RenderCtx.build(items, today_items)

    habits = [i for i in items if isinstance(i, Habit)]
    total_habits = len({h.id for h in habits if "vice" not in (h.tags or [])})

    upcoming_by_date: dict[date, list[dict[str, object]]] = {}
    for ev in upcoming_dates(within_days=2):
        ev_date = ctx.today + timedelta(days=ev["days_until"])
        upcoming_by_date.setdefault(ev_date, []).append(ev)

    today_habit_items = [i for i in (today_items or []) if isinstance(i, Habit)]
    checked_ids = {i.id for i in today_habit_items}
    all_habits = list({h.id: h for h in habits + today_habit_items}.values())

    today_str = ctx.today.isoformat()
    due_today_ids = {t.id for t in ctx.pending if t.scheduled_date and t.scheduled_date.isoformat() == today_str}

    lines: list[str] = []
    lines += section_header(ctx.today, tasks_today, habits_today, total_habits, added_today, deleted_today)
    lines += _section_done_today(ctx, today_items or [], all_habits, checked_ids, due_today_ids)
    lines += _habits(all_habits, checked_ids, ctx)
    lines += section_vices(all_habits, checked_ids, ctx)

    overdue = [
        t for t in ctx.pending if t.scheduled_date and t.scheduled_date < ctx.today and t.id not in ctx.subtask_ids
    ]
    if overdue:
        overdue_lines, _ = section_overdue(overdue, ctx)
        lines += overdue_lines

    lines += _today(ctx, today_str, upcoming_by_date.get(ctx.today, []))

    tomorrow = ctx.today + timedelta(days=1)
    due_tomorrow = [t for t in ctx.pending if t.scheduled_date and t.scheduled_date == tomorrow]
    tomorrow_lines, _ = section_schedule(due_tomorrow, "TOMORROW", ctx, events=upcoming_by_date.get(tomorrow, []))
    lines += tomorrow_lines

    return "\n".join(lines) + "\n"

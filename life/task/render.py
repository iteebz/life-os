"""Public render API — dashboard, timeline, detail, momentum."""

from datetime import date, timedelta

from life.task import task_sort_key
from life.task.minimal import render_minimal
from life.task.rows import (
    RenderCtx,
    fmt_tags,
    get_direct_tags,
    get_trend,
    row_task,
)
from life.task.sections import (
    section_backlog,
    section_done,
    section_done_today,
    section_habit_summary,
    section_header,
    section_overdue,
    section_schedule,
    section_vices,
)
from lifeos.core.lib import clock
from lifeos.core.lib.ansi import bold, dim, gold, gray, green, purple, red, theme, white
from lifeos.core.lib.dates import upcoming_dates
from lifeos.core.lib.format import fmt_time
from lifeos.core.models import Habit, Task, TaskMutation, Weekly

__all__ = [
    "render_dashboard",
    "render_day_summary",
    "render_minimal",
    "render_momentum",
    "render_task_detail",
]

_R = theme.reset
_GREY = theme.muted


def _pad_hm(t: str) -> str:
    """Zero-pad H:MM → HH:MM for stable lexicographic sort."""
    if ":" in t and len(t.split(":", 1)[0]) == 1:
        return "0" + t
    return t


def _section_today_outstanding(
    ctx: RenderCtx,
    all_habits: list[Habit],
    checked_ids: set[str],
    today_str: str,
    events: list[dict[str, object]],
) -> tuple[list[str], set[str]]:
    """Outstanding today: untimed-checked habits skipped, only what's left + now-marker."""
    now_dt = clock.now()
    now_time = now_dt.strftime("%H:%M")
    now_display = fmt_time(now_dt)

    timed: list[tuple[str, int, list[str]]] = []
    scheduled_ids: set[str] = set()

    due_today = [t for t in ctx.pending if t.scheduled_date and t.scheduled_date.isoformat() == today_str]
    for task in due_today:
        t_str = _pad_hm(task.scheduled_time) if task.scheduled_time else "zz:zz"
        rows = row_task(task, ctx, {}, show_date=False, show_parent=True)
        timed.append((t_str, 0, rows))
        scheduled_ids.add(task.id)
        for sub in ctx.subtasks.get(task.id, []):
            scheduled_ids.add(sub.id)

    event_emoji: dict[str, str] = {"birthday": "🎂", "anniversary": "💍", "deadline": "⚠️", "other": "📌"}
    for ev in events:
        emoji = event_emoji.get(str(ev.get("type", "")), "📌")
        timed.append(("zz:zz", 3, [f"  {emoji} {str(ev.get('name', '')).lower()}"]))

    timed.sort(key=lambda x: (x[0], x[1]))

    total_today = len(due_today) + len(events)
    lines = [f"\n{bold(gold(f'TODAY ({total_today})'))}"]

    now_inserted = False
    for t_str, _, rows in timed:
        if not now_inserted and (t_str == "zz:zz" or (t_str != "~~:~~" and t_str > now_time)):
            lines.append(f"  {gray('─')} {theme.coral}▸ {now_display}{gray(' ──────────────')}{_R}")
            now_inserted = True
        lines.extend(rows)

    if not now_inserted:
        lines.append(f"  {gray('─')} {theme.coral}▸ {now_display}{gray(' ──────────────')}{_R}")

    return lines, scheduled_ids


def render_dashboard(
    items: list[Task | Habit],
    today_breakdown: tuple[int, int, int, int],
    today_items: list[Task | Habit] | None = None,
) -> str:
    habits_today, tasks_today, added_today, deleted_today = today_breakdown
    ctx = RenderCtx.build(items, today_items)

    habits = [i for i in items if isinstance(i, Habit)]
    total_habits = len({h.id for h in habits if "vice" not in (h.tags or [])})

    upcoming_by_date: dict[date, list[dict[str, object]]] = {}
    for ev in upcoming_dates(within_days=7):
        ev_date = ctx.today + timedelta(days=ev["days_until"])
        upcoming_by_date.setdefault(ev_date, []).append(ev)

    today_habit_items = [i for i in (today_items or []) if isinstance(i, Habit)]
    checked_ids = {i.id for i in today_habit_items}
    all_habits = list({h.id: h for h in habits + today_habit_items}.values())

    lines: list[str] = []
    lines += section_header(ctx.today, tasks_today, habits_today, total_habits, added_today, deleted_today)

    today_str = ctx.today.isoformat()
    due_today_ids = {t.id for t in ctx.pending if t.scheduled_date and t.scheduled_date.isoformat() == today_str}
    lines += section_done_today(ctx, today_items or [], all_habits, checked_ids, due_today_ids)
    today_lines, scheduled_ids = _section_today_outstanding(
        ctx, all_habits, checked_ids, today_str, upcoming_by_date.get(ctx.today, [])
    )
    lines += today_lines

    overdue = [
        t for t in ctx.pending if t.scheduled_date and t.scheduled_date < ctx.today and t.id not in ctx.subtask_ids
    ]
    if overdue:
        overdue_lines, overdue_ids = section_overdue(overdue, ctx)
        lines += overdue_lines
        scheduled_ids |= overdue_ids

    lines += section_habit_summary(all_habits, checked_ids, ctx)
    lines += section_vices(all_habits, checked_ids, ctx)

    for offset in range(1, 15):
        day = ctx.today + timedelta(days=offset)
        if offset == 1:
            label = "TOMORROW"
        elif offset <= 7:
            label = day.strftime("%A").upper()
        else:
            label = day.strftime("%-d %b").upper()
        due_day = [t for t in ctx.pending if t.scheduled_date and t.scheduled_date == day]
        day_lines, day_ids = section_schedule(due_day, label, ctx, events=upcoming_by_date.get(day, []))
        lines += day_lines
        scheduled_ids |= day_ids

    completed_today_tasks = [i for i in (today_items or []) if isinstance(i, Task)]
    completed_subs: dict[str, list[Task]] = {}
    for t in completed_today_tasks:
        if t.parent_id:
            completed_subs.setdefault(t.parent_id, []).append(t)

    ctx.scheduled_ids = scheduled_ids
    backlog = [i for i in items if isinstance(i, Task) and i.id not in scheduled_ids and i.id not in ctx.subtask_ids]
    lines += section_backlog(backlog, ctx, completed_subs)

    return "\n".join(lines) + "\n"


def render_day_summary(
    target_date: date,
    completed_items: list[Task | Habit],
    breakdown: tuple[int, int, int, int],
    mood: tuple[int, str | None] | None = None,
    total_habits: int = 0,
) -> str:
    habits_done, tasks_done, added, deleted = breakdown
    ctx = RenderCtx.build(completed_items)

    lines = [f"\n{bold(white(target_date.strftime('%a') + ' · ' + target_date.strftime('%-d %b %Y')))}"]
    lines.append(f"{_GREY}tasks:{_R} {green(str(tasks_done))}")
    habits_total_str = f"{_GREY}/{total_habits}{_R}" if total_habits else ""
    lines.append(f"{_GREY}habits:{_R} {purple(str(habits_done))}{habits_total_str}")
    if added:
        lines.append(f"{_GREY}added:{_R} {gold(str(added))}")
    if deleted:
        lines.append(f"{_GREY}removed:{_R} {red(str(deleted))}")
    if mood:
        score, label = mood
        bar = "█" * score + "░" * (5 - score)
        label_str = f"  {label}" if label else ""
        lines.append(f"{_GREY}mood:{_R} {bar}  {score}/5{label_str}")

    if not completed_items:
        lines.append(f"\n  {gray('nothing completed.')}")
        return "\n".join(lines) + "\n"

    done_lines = section_done(completed_items, ctx, target_date=target_date, show_header=False)
    if done_lines:
        lines.append("")
        lines += done_lines

    return "\n".join(lines) + "\n"


def render_momentum(momentum: dict[str, Weekly]) -> str:
    lines = [f"\n{bold(white('MOMENTUM:'))}"]
    for week_name in ["this_week", "last_week", "prior_week"]:
        w = momentum[week_name]
        tasks_rate = (w.tasks_completed / w.tasks_total) * 100 if w.tasks_total > 0 else 0
        habits_rate = (w.habits_completed / w.habits_total) * 100 if w.habits_total > 0 else 0
        lines.append(f"  {week_name.replace('_', ' ')}:")
        lines.append(f"    tasks: {w.tasks_completed}/{w.tasks_total} ({tasks_rate:.0f}%)")
        lines.append(f"    habits: {w.habits_completed}/{w.habits_total} ({habits_rate:.0f}%)")
    if "this_week" in momentum and "last_week" in momentum:
        lines.append(f"\n{bold(white('TRENDS (vs. Last Week):'))}")
        tw, lw = momentum["this_week"], momentum["last_week"]
        task_trend = get_trend(tw.tasks_completed, lw.tasks_completed)
        habit_trend = get_trend(tw.habits_completed, lw.habits_completed)
        lines.append(f"  Tasks: {task_trend}")
        lines.append(f"  Habits: {habit_trend}")
    return "\n".join(lines)


def _block_task(
    task: Task,
    subtasks: list[Task],
    ctx: RenderCtx,
    mutations: list[TaskMutation] | None = None,
    indent: str = "",
) -> list[str]:
    tags_str = fmt_tags(task.tags, ctx.tag_colors)
    focus_str = f"{theme.bold}→{_R} " if task.focus else ""
    fire_str = f"{theme.bold}🔥{_R} " if task.is_urgent else ""
    status = gray("✓") if task.completed_at else "□"
    lines = [f"{indent}{status} {focus_str}{fire_str}{dim('[' + task.id[:8] + ']')}  {task.content.lower()}{tags_str}"]

    if task.scheduled_date:
        label = "deadline" if task.is_deadline else "scheduled"
        date_str = task.scheduled_date.isoformat()
        if task.scheduled_time:
            date_str += f" {fmt_time(task.scheduled_time)}"
        lines.append(f"{indent}  {red(label) if task.is_deadline else label}: {date_str}")
    if task.notes:
        lines.append(f"{indent}  {task.notes}")
    if task.blocked_by:
        lines.append(f"{indent}  blocked by: {task.blocked_by[:8]}")

    for sub in sorted(subtasks, key=task_sort_key):
        sub_status = gray("✓") if sub.completed_at else "□"
        sub_tags_str = fmt_tags(get_direct_tags(sub, ctx.pending), ctx.tag_colors)
        time_str = f"{dim(fmt_time(sub.scheduled_time))} " if sub.scheduled_time else ""
        lines.append(
            f"{indent}  └ {sub_status} {dim('[' + sub.id[:8] + ']')}  {time_str}{sub.content.lower()}{sub_tags_str}"
        )

    deferrals = [m for m in (mutations or []) if m.field == "defer" or m.reason == "overdue_reset"]
    if deferrals:
        lines.append(f"{indent}  deferrals:")
        for m in deferrals:
            reason = f" — {m.reason}" if m.reason else ""
            lines.append(f"{indent}    {m.mutated_at.strftime('%Y-%m-%d')}{reason}")
    return lines


def render_task_detail(
    task: Task,
    subtasks: list[Task],
    mutations: list[TaskMutation] | None = None,
    parent: Task | None = None,
    parent_subtasks: list[Task] | None = None,
) -> str:
    all_tasks = [task, *subtasks, *(parent_subtasks or []), *([parent] if parent else [])]
    ctx = RenderCtx.build(all_tasks)
    if parent:
        lines = _block_task(parent, parent_subtasks or [], ctx)
    else:
        lines = _block_task(task, subtasks, ctx, mutations)
    return "\n".join(lines)

"""Public render API — dashboard, timeline, detail, momentum."""

from datetime import date, timedelta

from life.core.models import Habit, Task, TaskMutation, Weekly
from life.lib import clock
from life.lib.ansi import bold, dim, gold, gray, green, purple, red, theme, white
from life.lib.dates import upcoming_dates
from life.lib.format import fmt_time
from life.task import task_sort_key
from life.task.rows import (
    RenderCtx,
    fmt_tags,
    get_direct_tags,
    get_trend,
    row_habit,
    row_task,
)
from life.task.sections import (
    section_backlog,
    section_daily,
    section_done,
    section_header,
    section_hobbies,
    section_overdue,
    section_schedule,
    section_untagged,
    section_vices,
    section_weekly,
    tag_section,
)

__all__ = [
    "render_dashboard",
    "render_day_summary",
    "render_momentum",
    "render_task_detail",
    "render_timeline",
]

_R = theme.reset
_GREY = theme.muted


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
    for ev in upcoming_dates(within_days=14):
        ev_date = ctx.today + timedelta(days=ev["days_until"])
        upcoming_by_date.setdefault(ev_date, []).append(ev)

    lines: list[str] = []
    lines += section_header(ctx.today, tasks_today, habits_today, total_habits, added_today, deleted_today)

    done_lines = section_done(today_items or [], ctx)
    if done_lines:
        lines.append("")
        lines += done_lines

    overdue = [
        t for t in ctx.pending if t.scheduled_date and t.scheduled_date < ctx.today and t.id not in ctx.subtask_ids
    ]
    scheduled_ids: set[str] = set()
    if overdue:
        overdue_lines, overdue_ids = section_overdue(overdue, ctx)
        lines += overdue_lines
        scheduled_ids |= overdue_ids

    today_str = ctx.today.isoformat()
    due_today = [t for t in ctx.pending if t.scheduled_date and t.scheduled_date.isoformat() == today_str]
    today_lines, today_ids = section_schedule(
        due_today, "TODAY", ctx, is_today=True, events=upcoming_by_date.get(ctx.today, [])
    )
    lines += today_lines
    scheduled_ids |= today_ids

    today_habit_items = [i for i in (today_items or []) if isinstance(i, Habit)]
    checked_ids = {i.id for i in today_habit_items}
    all_habits = list(set(habits + today_habit_items))
    lines += section_daily(all_habits, checked_ids, ctx)
    lines += tag_section(all_habits, checked_ids, ctx, "love", "LOVE", theme.pink)
    lines += tag_section(all_habits, checked_ids, ctx, "admin", "LIFE", theme.yellow)
    lines += tag_section(all_habits, checked_ids, ctx, "chore", "CHORES", theme.cyan)
    lines += section_hobbies(all_habits, checked_ids, ctx)
    lines += section_weekly(all_habits, checked_ids, ctx)
    lines += section_untagged(all_habits, checked_ids, ctx)
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


def render_timeline(
    items: list[Task | Habit],
    today_items: list[Task | Habit] | None = None,
) -> str:
    ctx = RenderCtx.build(items, today_items)
    habits = [i for i in items if isinstance(i, Habit)]
    today_habit_items = [i for i in (today_items or []) if isinstance(i, Habit)]
    checked_ids = {i.id for i in today_habit_items}
    all_habits = list({h.id: h for h in habits + today_habit_items}.values())

    now_time = clock.now().strftime("%H:%M")
    now_display = fmt_time(clock.now())
    today_str = ctx.today.isoformat()
    header = ctx.today.strftime("%a") + " · " + ctx.today.strftime("%-d %b %Y") + " · " + now_display
    lines = [f"\n{bold(white('TIMELINE · ' + header))}\n"]

    timed: list[tuple[str, int, list[str], bool]] = []

    overdue = [
        t for t in ctx.pending if t.scheduled_date and t.scheduled_date < ctx.today and t.id not in ctx.subtask_ids
    ]

    due_today = [
        t
        for t in ctx.pending
        if t.scheduled_date and t.scheduled_date.isoformat() == today_str and t.id not in ctx.subtask_ids
    ]
    for task in due_today:
        t_str = task.scheduled_time or "00:00"
        rows = row_task(task, ctx, {}, show_date=False, show_parent=True)
        timed.append((t_str, 0, rows, False))
        ctx.scheduled_ids.add(task.id)

    completed_tasks = [i for i in (today_items or []) if isinstance(i, Task) and i.completed_at]
    timed_task_ids = {task.id for task in due_today}
    for task in completed_tasks:
        if task.id in timed_task_ids:
            continue
        t_sort = task.completed_at.strftime("%H:%M")  # type: ignore[union-attr]
        t_disp = fmt_time(task.completed_at)  # type: ignore[union-attr]
        tags_str = fmt_tags(task.tags, ctx.tag_colors)
        id_str = f" {dim('[' + task.id[:8] + ']')}"
        row = f"  {dim(green('✓') + ' ' + gray(t_disp) + ' ' + task.content.lower() + tags_str + id_str)}"
        timed.append((t_sort, 0, [row], True))

    floating_habits: list[Habit] = []
    placed_habit_ids: set[str] = set()
    for habit in all_habits:
        if habit.private or habit.parent_id or habit.cadence == "weekly" or "vice" in (habit.tags or []):
            continue
        if habit.id in checked_ids:
            today_checks = [c for c in habit.checks if c.date() == ctx.today]
            t_str = max(today_checks).strftime("%H:%M") if today_checks else (habit.scheduled_time or now_time)
            rows = row_habit(habit, checked_ids, ctx)
            timed.append((t_str, 1, rows, True))
            placed_habit_ids.add(habit.id)
        elif habit.scheduled_time:
            rows = row_habit(habit, checked_ids, ctx)
            timed.append((habit.scheduled_time, 1, rows, False))
            placed_habit_ids.add(habit.id)
        elif "chore" in (habit.tags or []):
            rows = row_habit(habit, checked_ids, ctx)
            if habit.id in checked_ids:
                today_checks = [c for c in habit.checks if c.date() == ctx.today]
                t_str = max(today_checks).strftime("%H:%M") if today_checks else now_time
                timed.append((t_str, 2, rows, True))
            else:
                timed.append(("~~:~~", 2, rows, False))
            placed_habit_ids.add(habit.id)
        else:
            floating_habits.append(habit)

    timed.sort(key=lambda x: (x[0], x[1]))

    now_inserted = False
    for t_str, _, rows, is_done in timed:
        if not now_inserted and t_str > now_time:
            lines.append(f"  {gray('─')} {theme.coral}▸ {now_display}{gray(' ─────────────────────')}{_R}")
            now_inserted = True
        if not is_done:
            lines.extend(f"{theme.bold}{r}{_R}" for r in rows)
        else:
            lines.extend(rows)

    if not now_inserted:
        lines.append(f"  {gray('─')} {theme.coral}▸ {now_time}{gray(' ─────────────────────')}{_R}")

    if overdue:
        lines.append(f"\n{bold(red('OVERDUE'))}")
        for task in sorted(overdue, key=task_sort_key):
            lines.extend(row_task(task, ctx, {}))

    if floating_habits:
        lines.append(f"\n{bold(purple('FLOATING'))}")
        for habit in sorted(floating_habits, key=lambda h: (h.tags[0] if h.tags else "", h.content.lower())):
            lines.extend(row_habit(habit, checked_ids, ctx))

    lines += section_weekly(all_habits, checked_ids, ctx)

    return "\n".join(lines) + "\n"


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

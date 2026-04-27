import dataclasses
import random
from collections.abc import Sequence
from datetime import date, datetime, timedelta

from life.core.models import Habit, Task, TaskMutation, Weekly
from life.domain.habit import get_subhabits
from life.task import task_sort_key

from life.lib import clock
from life.lib.ansi import POOL, bold, dim, gold, gray, green, purple, red, theme, white
from life.lib.dates import upcoming_dates

__all__ = [
    "render_dashboard",
    "render_day_summary",
    "render_momentum",
    "render_task_detail",
]

TAG_ORDER = ["finance", "legal", "janice", "comms", "home", "income"]
# Tags that act as auxiliary labels — never primary if another tag exists
AUX_TAGS = {"comms"}

_R = theme.reset
_GREY = theme.muted


# ── primitives ────────────────────────────────────────────────────────────────


def _primary_tag(task: Task) -> str | None:
    tags = task.tags or []
    non_aux = [t for t in tags if t not in AUX_TAGS]
    candidates = non_aux or tags
    for tag in TAG_ORDER:
        if tag in candidates:
            return tag
    return sorted(candidates)[0] if candidates else None


def _fmt_time(t: str) -> str:
    return f"{theme.gray}{t}{_R}"


def _fmt_rel_date(
    due: date, today: date, time: str | None = None, is_deadline: bool = False
) -> str:
    delta = (due - today).days
    if delta <= 7:
        day_label = due.strftime("%a").lower()
        label = f"{day_label}·{time}" if time else day_label
    else:
        label = f"+{delta}d"
    return red(label) if is_deadline else label


def _fmt_tags(tags: list[str], tag_colors: dict[str, str]) -> str:
    if not tags:
        return ""
    return " " + " ".join(f"{tag_colors.get(t, _GREY)}#{t}{_R}" for t in tags)


def _get_direct_tags(task: Task, pending: list[Task]) -> list[str]:
    if not task.parent_id:
        return task.tags
    parent = next((t for t in pending if t.id == task.parent_id), None)
    if not parent:
        return task.tags
    return [tag for tag in task.tags if tag not in parent.tags]


def _build_tag_colors(items: Sequence[Task | Habit]) -> dict[str, str]:
    tags = sorted({tag for item in items for tag in item.tags})
    pool = random.sample([code for code, _ in POOL], len(POOL))
    return {tag: pool[i % len(pool)] for i, tag in enumerate(tags)}


def _get_trend(current: int, previous: int) -> str:
    if previous == 0:
        return "↗" if current > 0 else "→"
    return "↗" if current > previous else "↘" if current < previous else "→"


# ── render context ────────────────────────────────────────────────────────────


@dataclasses.dataclass
class RenderCtx:
    today: date
    tag_colors: dict[str, str]
    pending: list[Task]
    subtasks: dict[str, list[Task]]  # parent_id → children
    id_to_content: dict[str, str]  # task_id → content
    subtask_ids: set[str]  # IDs that are subtasks
    scheduled_ids: set[str] = dataclasses.field(default_factory=set)

    @classmethod
    def build(
        cls,
        items: Sequence[Task | Habit],
        today_items: Sequence[Task | Habit] | None = None,
    ) -> "RenderCtx":
        today = clock.today()
        pending = [i for i in items if isinstance(i, Task)]
        tag_colors = _build_tag_colors(list(items) + list(today_items or []))
        subtasks: dict[str, list[Task]] = {}
        for t in pending:
            if t.parent_id:
                subtasks.setdefault(t.parent_id, []).append(t)
        return cls(
            today=today,
            tag_colors=tag_colors,
            pending=pending,
            subtasks=subtasks,
            id_to_content={t.id: t.content for t in pending},
            subtask_ids={t.id for t in pending if t.parent_id},
        )


# ── row renderers ─────────────────────────────────────────────────────────────


def _row_subtask(sub: Task, ctx: RenderCtx, indent: str = "  └ ") -> str:
    id_str = f" {dim('[' + sub.id[:8] + ']')}"
    tags_str = _fmt_tags(_get_direct_tags(sub, ctx.pending), ctx.tag_colors)
    time_str = f"{_fmt_time(sub.scheduled_time)} " if sub.scheduled_time else ""
    return f"{indent}□ {time_str}{sub.content.lower()}{tags_str}{id_str}{_R}"


def _row_task(
    task: Task,
    ctx: RenderCtx,
    completed_subs: dict[str, list[Task]],
    indent: str = "  ",
    tags_override: list[str] | None = None,
    show_date: bool = True,
    show_parent: bool = False,
) -> list[str]:
    today_str = ctx.today.isoformat()
    tomorrow_str = (ctx.today + timedelta(days=1)).isoformat()
    tags_str = _fmt_tags(tags_override if tags_override is not None else task.tags, ctx.tag_colors)
    id_str = f" {dim('[' + task.id[:8] + ']')}"

    if show_date:
        prefix = ""
        if task.scheduled_date and task.scheduled_date.isoformat() not in (today_str, tomorrow_str):
            prefix = (
                _fmt_rel_date(task.scheduled_date, ctx.today, task.scheduled_time, task.is_deadline)
                + " "
            )
    else:
        prefix = f"{_fmt_time(task.scheduled_time)} " if task.scheduled_time else ""

    parent_str = ""
    if show_parent and task.parent_id:
        parent_name = ctx.id_to_content.get(task.parent_id, "")
        if parent_name:
            parent_str = f" {dim('~ ' + parent_name.lower())}"

    if task.blocked_by:
        blocker = ctx.id_to_content.get(task.blocked_by, task.blocked_by[:8])
        blocker_str = dim("← " + blocker.lower())
        content = f"{_GREY}{prefix}{task.content.lower()}{tags_str}{_R}"
        row = f"{indent}⊘ {content} {blocker_str}{id_str}"
    else:
        fire = f"{theme.bold}🔥{_R} " if task.focus else ""
        row = f"{indent}□ {fire}{prefix}{task.content.lower()}{tags_str}{id_str}{parent_str}"

    rows = [row]
    rows.extend(
        _row_subtask(sub, ctx, indent=f"{indent}└ ")
        for sub in sorted(ctx.subtasks.get(task.id, []), key=task_sort_key)
        if sub.id not in ctx.scheduled_ids
    )
    for sub in completed_subs.get(task.id, []):
        tags_str2 = _fmt_tags(_get_direct_tags(sub, ctx.pending), ctx.tag_colors)
        time_str = f"{_fmt_time(sub.scheduled_time)} " if sub.scheduled_time else ""
        rows.append(
            f"{indent}  {gray('└ ' + time_str + '✓ ' + sub.content.lower())}{tags_str2}{id_str}"
        )
    return rows


def _row_habit(
    habit: Habit, checked_ids: set[str], ctx: RenderCtx, indent: str = "  "
) -> list[str]:
    tags_str = _fmt_tags(habit.tags, ctx.tag_colors)
    id_str = f" {dim('[' + habit.id[:8] + ']')}"

    if habit.cadence == "weekly":
        # Trend: last 4 weeks vs prior 4 weeks
        def _weeks_hit(start: date, end: date) -> int:
            dates = {dt.date() for dt in habit.checks if start <= dt.date() <= end}
            return len({d.isocalendar()[1] for d in dates})

        p1_start = ctx.today - timedelta(weeks=4)
        p2_start = ctx.today - timedelta(weeks=8)
        p2_end = p1_start - timedelta(days=1)
        count_p1 = _weeks_hit(p1_start, ctx.today)
        count_p2 = _weeks_hit(p2_start, p2_end)
        cadence_label = f" {gray('(weekly)')}"
    else:
        p1_start = ctx.today - timedelta(days=6)
        p2_start = ctx.today - timedelta(days=13)
        p2_end = p1_start - timedelta(days=1)
        count_p1 = sum(1 for dt in habit.checks if p1_start <= dt.date() <= ctx.today)
        count_p2 = sum(1 for dt in habit.checks if p2_start <= dt.date() <= p2_end)
        cadence_label = ""

    trend = "↗" if count_p1 > count_p2 else "↘" if count_p1 < count_p2 else "→"
    time_str = f" {gray(habit.scheduled_time)}" if habit.scheduled_time else ""
    if habit.id in checked_ids:
        label = f"{gray(habit.content.lower())}{cadence_label}{tags_str}"
        lines = [f"{indent}{purple('●')} {gray(trend)} {label}{time_str}{id_str}"]
    else:
        label = f"{habit.content.lower()}{cadence_label}{tags_str}"
        lines = [f"{indent}{purple('○')} {gray(trend)} {label}{time_str}{id_str}"]
    for sub in get_subhabits(habit.id):
        lines.extend(_row_habit(sub, checked_ids, ctx, indent="   └ "))
    return lines


# ── sections ──────────────────────────────────────────────────────────────────


def _section_header(
    today: date, tasks_done: int, habits_done: int, total_habits: int, added: int, deleted: int
) -> list[str]:
    time_str = clock.now().strftime("%H:%M")
    header = today.strftime("%a") + " · " + today.strftime("%-d %b %Y") + " · " + time_str
    lines = [f"\n{bold(white(header))}"]
    lines.append(f"{_GREY}tasks:{_R} {green(str(tasks_done))}")
    lines.append(f"{_GREY}habits:{_R} {purple(str(habits_done))}{_GREY}/{total_habits}{_R}")
    if added:
        lines.append(f"{_GREY}added:{_R} {gold(str(added))}")
    if deleted:
        lines.append(f"{_GREY}removed:{_R} {red(str(deleted))}")
    return lines


def _section_done(
    items: list[Task | Habit],
    ctx: RenderCtx,
    target_date: date | None = None,
    show_header: bool = True,
) -> list[str]:
    if not items:
        return []
    target = target_date or ctx.today

    def _sort_key(item: Task | Habit) -> datetime:
        if isinstance(item, Task) and item.completed_at:
            return item.completed_at
        if isinstance(item, Habit) and item.checks:
            day_checks = [c for c in item.checks if c.date() == target]
            if day_checks:
                return max(day_checks)
            return max(item.checks)
        return item.created

    lines = [bold(green(f"DONE ({len(items)})"))] if show_header else []
    for item in sorted(items, key=_sort_key):
        tags_str = _fmt_tags(item.tags, ctx.tag_colors)
        content = item.content.lower()
        id_str = f" {dim('[' + item.id[:8] + ']')}"
        if isinstance(item, Habit):
            on_date = [c for c in item.checks if c.date() == target]
            time_str = max(on_date).strftime("%H:%M") if on_date else ""
            lines.append(f"  {purple('●')} {_GREY}{time_str}{_R} {content}{tags_str}{id_str}")
        elif item.completed_at:
            time_str = item.completed_at.strftime("%H:%M")
            parent_str = ""
            if item.parent_id:
                parent = next((t for t in ctx.pending if t.id == item.parent_id), None)
                if parent and not parent.completed_at:
                    parent_str = f" {dim('→ ' + parent.content.lower())}"
            lines.append(
                f"  {green('✓')} {_GREY}{time_str}{_R} {content}{tags_str}{id_str}{parent_str}"
            )
    return lines


def _section_overdue(tasks: list[Task], ctx: RenderCtx) -> tuple[list[str], set[str]]:
    lines = [f"\n{theme.bold}{theme.red}OVERDUE{_R}"]
    scheduled_ids: set[str] = set()
    for task in sorted(tasks, key=task_sort_key):
        scheduled_ids.add(task.id)
        lines.extend(_row_task(task, ctx, {}))
        for sub in ctx.subtasks.get(task.id, []):
            scheduled_ids.add(sub.id)
    return lines, scheduled_ids


_EVENT_EMOJI: dict[str, str] = {
    "birthday": "🎂",
    "anniversary": "💍",
    "deadline": "⚠️",
    "other": "📌",
}


def _section_schedule(
    tasks: list[Task],
    label: str,
    ctx: RenderCtx,
    is_today: bool = False,
    events: list[dict[str, object]] | None = None,
) -> tuple[list[str], set[str]]:
    all_events = events or []
    if not tasks and not all_events:
        if is_today:
            return [f"\n{bold(gold(label + ' (0)'))}", f"  {gray('nothing scheduled.')}"], set()
        return [], set()

    count = len(tasks) + len(all_events)
    header_color = gold if is_today else white
    lines = [f"\n{bold(header_color(label + f' ({count})'))}"]
    scheduled_ids: set[str] = set()

    def _sort(t: Task) -> tuple[int, str, bool]:
        return (0, t.scheduled_time, not t.focus) if t.scheduled_time else (1, "", not t.focus)

    for task in sorted(tasks, key=_sort):
        scheduled_ids.add(task.id)
        lines.extend(_row_task(task, ctx, {}, show_date=False, show_parent=True))
        for sub in ctx.subtasks.get(task.id, []):
            scheduled_ids.add(sub.id)

    for event in all_events:
        emoji = _EVENT_EMOJI.get(str(event.get("type", "")), "📌")
        lines.append(f"  {emoji} {str(event.get('name', '')).lower()}")

    return lines, scheduled_ids


def _section_habits(habits: list[Habit], checked_ids: set[str], ctx: RenderCtx) -> list[str]:
    visible = [h for h in habits if not h.private and not h.parent_id]
    if not visible:
        return []

    # Weekly habits count as "done" if checked any day this week
    week_start = ctx.today - timedelta(days=ctx.today.weekday())

    def _is_done(h: Habit) -> bool:
        if h.id in checked_ids:
            return True
        if h.cadence == "weekly":
            return any(week_start <= dt.date() <= ctx.today for dt in h.checks)
        return False

    done_count = sum(1 for h in visible if _is_done(h))
    remaining = [h for h in visible if not _is_done(h)]

    lines = [f"\n{theme.bold}{theme.purple}HABITS ({done_count}/{len(visible)}){_R}"]
    if not remaining:
        lines.append(f"  {gray('all done.')}")
        return lines
    def _habit_sort_key(h: Habit) -> tuple[int, str]:
        return (1 if h.scheduled_time else 0, h.scheduled_time or h.content.lower())

    for habit in sorted(remaining, key=_habit_sort_key):
        lines.extend(_row_habit(habit, checked_ids, ctx))
    return lines


def _section_backlog(
    tasks: list[Task],
    ctx: RenderCtx,
    completed_subs: dict[str, list[Task]],
) -> list[str]:
    if not tasks:
        return []
    groups: dict[str, list[Task]] = {}
    for task in sorted(tasks, key=lambda t: t.content.lower()):
        groups.setdefault(_primary_tag(task) or "", []).append(task)

    sections = [t for t in TAG_ORDER if t in groups]
    sections += sorted(k for k in groups if k and k not in TAG_ORDER)
    if "" in groups:
        sections.append("")

    lines: list[str] = []
    for tag in sections:
        label = tag.upper() if tag else "BACKLOG"
        color = ctx.tag_colors.get(tag, theme.white) if tag else theme.white
        lines.append(f"\n{theme.bold}{color}{label} ({len(groups[tag])}){_R}")
        for task in groups[tag]:
            lines.extend(_row_task(task, ctx, completed_subs, tags_override=task.tags))
    return lines


# ── views ─────────────────────────────────────────────────────────────────────


def render_dashboard(
    items: list[Task | Habit],
    today_breakdown: tuple[int, int, int, int],
    today_items: list[Task | Habit] | None = None,
) -> str:
    habits_today, tasks_today, added_today, deleted_today = today_breakdown
    ctx = RenderCtx.build(items, today_items)

    habits = [i for i in items if isinstance(i, Habit)]
    total_habits = len({h.id for h in habits})

    upcoming_by_date: dict[date, list[dict[str, object]]] = {}
    for ev in upcoming_dates(within_days=14):
        ev_date = ctx.today + timedelta(days=ev["days_until"])
        upcoming_by_date.setdefault(ev_date, []).append(ev)

    lines: list[str] = []
    lines += _section_header(
        ctx.today, tasks_today, habits_today, total_habits, added_today, deleted_today
    )

    done_lines = _section_done(today_items or [], ctx)
    if done_lines:
        lines.append("")
        lines += done_lines

    overdue = [
        t
        for t in ctx.pending
        if t.scheduled_date and t.scheduled_date < ctx.today and t.id not in ctx.subtask_ids
    ]
    scheduled_ids: set[str] = set()
    if overdue:
        overdue_lines, overdue_ids = _section_overdue(overdue, ctx)
        lines += overdue_lines
        scheduled_ids |= overdue_ids

    today_str = ctx.today.isoformat()
    due_today = [
        t for t in ctx.pending if t.scheduled_date and t.scheduled_date.isoformat() == today_str
    ]
    today_lines, today_ids = _section_schedule(
        due_today, "TODAY", ctx, is_today=True, events=upcoming_by_date.get(ctx.today, [])
    )
    lines += today_lines
    scheduled_ids |= today_ids

    today_habit_items = [i for i in (today_items or []) if isinstance(i, Habit)]
    checked_ids = {i.id for i in today_habit_items}
    all_habits = list(set(habits + today_habit_items))
    lines += _section_habits(all_habits, checked_ids, ctx)

    for offset in range(1, 15):
        day = ctx.today + timedelta(days=offset)
        if offset == 1:
            label = "TOMORROW"
        elif offset <= 7:
            label = day.strftime("%A").upper()
        else:
            label = day.strftime("%-d %b").upper()
        due_day = [t for t in ctx.pending if t.scheduled_date and t.scheduled_date == day]
        day_lines, day_ids = _section_schedule(
            due_day, label, ctx, events=upcoming_by_date.get(day, [])
        )
        lines += day_lines
        scheduled_ids |= day_ids

    completed_today_tasks = [i for i in (today_items or []) if isinstance(i, Task)]
    completed_subs: dict[str, list[Task]] = {}
    for t in completed_today_tasks:
        if t.parent_id:
            completed_subs.setdefault(t.parent_id, []).append(t)

    ctx.scheduled_ids = scheduled_ids
    backlog = [
        i
        for i in items
        if isinstance(i, Task) and i.id not in scheduled_ids and i.id not in ctx.subtask_ids
    ]
    lines += _section_backlog(backlog, ctx, completed_subs)

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

    lines = [
        f"\n{bold(white(target_date.strftime('%a') + ' · ' + target_date.strftime('%-d %b %Y')))}"
    ]
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

    done_lines = _section_done(completed_items, ctx, target_date=target_date, show_header=False)
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
        task_trend = _get_trend(tw.tasks_completed, lw.tasks_completed)
        habit_trend = _get_trend(tw.habits_completed, lw.habits_completed)
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
    tags_str = _fmt_tags(task.tags, ctx.tag_colors)
    focus_str = f"{theme.bold}🔥{_R} " if task.focus else ""
    status = gray("✓") if task.completed_at else "□"
    lines = [
        f"{indent}{status} {focus_str}{dim('[' + task.id[:8] + ']')}  "
        f"{task.content.lower()}{tags_str}"
    ]

    if task.scheduled_date:
        label = "deadline" if task.is_deadline else "scheduled"
        date_str = task.scheduled_date.isoformat()
        if task.scheduled_time:
            date_str += f" {_fmt_time(task.scheduled_time)}"
        lines.append(f"{indent}  {red(label) if task.is_deadline else label}: {date_str}")
    if task.notes:
        lines.append(f"{indent}  {task.notes}")
    if task.blocked_by:
        lines.append(f"{indent}  blocked by: {task.blocked_by[:8]}")

    for sub in sorted(subtasks, key=task_sort_key):
        sub_status = gray("✓") if sub.completed_at else "□"
        sub_tags_str = _fmt_tags(_get_direct_tags(sub, ctx.pending), ctx.tag_colors)
        time_str = f"{dim(_fmt_time(sub.scheduled_time))} " if sub.scheduled_time else ""
        lines.append(
            f"{indent}  └ {sub_status} {dim('[' + sub.id[:8] + ']')}  "
            f"{time_str}{sub.content.lower()}{sub_tags_str}"
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

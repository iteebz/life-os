"""Row-level rendering primitives for tasks and habits."""

import dataclasses
import hashlib
from collections.abc import Sequence
from datetime import date, timedelta

from life.habit import get_subhabits
from life.task import task_sort_key
from lifeos.core.lib import clock
from lifeos.core.lib.ansi import NAMED_COLORS, POOL, dim, gray, green, purple, red, theme
from lifeos.core.lib.format import fmt_time
from lifeos.core.lib.tags import load_tag_groups, load_tag_overrides
from lifeos.core.models import Habit, Task

_DEFAULT_TAG_ORDER = ["finance", "legal", "janice", "comms", "home", "income"]

AUX_TAGS = {"comms"}

_R = theme.reset
_GREY = theme.muted


def get_tag_order() -> list[str]:
    groups = load_tag_groups()
    return [tag for tag, _ in groups] if groups else _DEFAULT_TAG_ORDER


def primary_tag(task: Task) -> str | None:
    tags = task.tags or []
    non_aux = [t for t in tags if t not in AUX_TAGS]
    candidates = non_aux or tags
    for tag in get_tag_order():
        if tag in candidates:
            return tag
    return sorted(candidates)[0] if candidates else None


def fmt_time_colored(t: str) -> str:
    return f"{theme.gray}{fmt_time(t)}{_R}"


def fmt_rel_date(due: date, today: date, time: str | None = None, is_deadline: bool = False) -> str:
    delta = (due - today).days
    if delta <= 7:
        day_label = due.strftime("%a").lower()
        label = f"{day_label}·{time}" if time else day_label
    else:
        label = f"+{delta}d"
    return red(label) if is_deadline else label


def fmt_tags(tags: list[str], tag_colors: dict[str, str]) -> str:
    if not tags:
        return ""
    return " " + " ".join(f"{tag_colors.get(t, _GREY)}#{t}{_R}" for t in tags)


def get_direct_tags(task: Task, pending: list[Task]) -> list[str]:
    if not task.parent_id:
        return task.tags
    parent = next((t for t in pending if t.id == task.parent_id), None)
    if not parent:
        return task.tags
    return [tag for tag in task.tags if tag not in parent.tags]


def _tag_hash(tag: str) -> int:
    return int(hashlib.md5(tag.encode()).hexdigest(), 16)


def build_tag_colors(items: Sequence[Task | Habit]) -> dict[str, str]:
    tags = sorted({tag for item in items for tag in item.tags})
    pool = [code for code, _ in POOL]
    n = len(pool)
    ordered = sorted(tags, key=_tag_hash)
    step = max(1, n // max(len(ordered), 1))
    colors = {tag: pool[(i * step) % n] for i, tag in enumerate(ordered)}
    for tag, color_name in load_tag_overrides().items():
        if tag in colors and color_name in NAMED_COLORS:
            colors[tag] = NAMED_COLORS[color_name]
    return colors


def get_trend(current: int, previous: int) -> str:
    if previous == 0:
        return "↗" if current > 0 else "→"
    return "↗" if current > previous else "↘" if current < previous else "→"


@dataclasses.dataclass
class RenderCtx:
    today: date
    tag_colors: dict[str, str]
    pending: list[Task]
    subtasks: dict[str, list[Task]]
    id_to_content: dict[str, str]
    subtask_ids: set[str]
    scheduled_ids: set[str] = dataclasses.field(default_factory=set)
    noted_ids: set[str] = dataclasses.field(default_factory=set)

    @classmethod
    def build(
        cls,
        items: Sequence[Task | Habit],
        today_items: Sequence[Task | Habit] | None = None,
    ) -> "RenderCtx":
        from life.note import get_noted_ids

        today = clock.today()
        pending = [i for i in items if isinstance(i, Task)]
        tag_colors = build_tag_colors(list(items) + list(today_items or []))
        subtasks: dict[str, list[Task]] = {}
        for t in pending:
            if t.parent_id:
                subtasks.setdefault(t.parent_id, []).append(t)
        all_items = list(items) + list(today_items or [])
        task_ids = [i.id for i in all_items if isinstance(i, Task)]
        habit_ids = [i.id for i in all_items if isinstance(i, Habit)]
        noted_ids = get_noted_ids("task", task_ids) | get_noted_ids("habit", habit_ids)
        return cls(
            today=today,
            tag_colors=tag_colors,
            pending=pending,
            subtasks=subtasks,
            id_to_content={t.id: t.content for t in pending},
            subtask_ids={t.id for t in pending if t.parent_id},
            noted_ids=noted_ids,
        )


def row_subtask(sub: Task, ctx: RenderCtx, indent: str = "  └ ") -> str:
    id_str = f" {dim('[' + sub.id[:8] + ']')}"
    tags_str = fmt_tags(get_direct_tags(sub, ctx.pending), ctx.tag_colors)
    time_str = f"{fmt_time_colored(sub.scheduled_time)} " if sub.scheduled_time else ""
    return f"{indent}□ {time_str}{sub.content.lower()}{tags_str}{id_str}{_R}"


def row_task(
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
    tags_str = fmt_tags(tags_override if tags_override is not None else task.tags, ctx.tag_colors)
    id_str = f" {dim('[' + task.id[:8] + ']')}"

    if show_date:
        prefix = ""
        if task.scheduled_date and task.scheduled_date.isoformat() not in (today_str, tomorrow_str):
            prefix = fmt_rel_date(task.scheduled_date, ctx.today, task.scheduled_time, task.is_deadline) + " "
    else:
        prefix = f"{fmt_time_colored(task.scheduled_time)} " if task.scheduled_time else ""

    parent_str = ""
    if show_parent and task.parent_id:
        parent_name = ctx.id_to_content.get(task.parent_id, "")
        if parent_name:
            parent_str = f" {dim('~ ' + parent_name.lower())}"

    notes_marker = f" {dim('»')}" if task.id in ctx.noted_ids else ""

    if task.blocked_by:
        blocker = ctx.id_to_content.get(task.blocked_by, task.blocked_by[:8])
        blocker_str = dim("← " + blocker.lower())
        content = f"{_GREY}{prefix}{task.content.lower()}{tags_str}{_R}"
        row = f"{indent}⊘ {content} {blocker_str}{id_str}{notes_marker}"
    else:
        focus_marker = f"{theme.bold}→{_R} " if task.focus else ""
        fire_marker = f"{theme.bold}🔥{_R} " if task.is_urgent else ""
        row = f"{indent}□ {focus_marker}{fire_marker}{prefix}{task.content.lower()}{tags_str}{id_str}{parent_str}{notes_marker}"

    rows = [row]
    rows.extend(
        row_subtask(sub, ctx, indent=f"{indent}└ ")
        for sub in sorted(ctx.subtasks.get(task.id, []), key=task_sort_key)
        if sub.id not in ctx.scheduled_ids
    )
    for sub in completed_subs.get(task.id, []):
        tags_str2 = fmt_tags(get_direct_tags(sub, ctx.pending), ctx.tag_colors)
        time_str = f"{fmt_time_colored(sub.scheduled_time)} " if sub.scheduled_time else ""
        rows.append(f"{indent}  {gray('└ ' + time_str + '✓ ' + sub.content.lower())}{tags_str2}{id_str}")
    return rows


def habit_counts(habit: Habit, today: date) -> tuple[int, int]:
    if habit.cadence == "weekly":

        def _weeks_hit(start: date, end: date) -> int:
            dates = {dt.date() for dt in habit.checks if start <= dt.date() <= end}
            return len({d.isocalendar()[1] for d in dates})

        p1_start = today - timedelta(weeks=4)
        p2_start = today - timedelta(weeks=8)
        p2_end = p1_start - timedelta(days=1)
        return _weeks_hit(p1_start, today), _weeks_hit(p2_start, p2_end)
    p1_start = today - timedelta(days=6)
    p2_start = today - timedelta(days=13)
    p2_end = p1_start - timedelta(days=1)
    return (
        sum(1 for dt in habit.checks if p1_start <= dt.date() <= today),
        sum(1 for dt in habit.checks if p2_start <= dt.date() <= p2_end),
    )


def row_habit(habit: Habit, checked_ids: set[str], ctx: RenderCtx, indent: str = "  ") -> list[str]:
    tags_str = fmt_tags(habit.tags, ctx.tag_colors)
    id_str = f" {dim('[' + habit.id[:8] + ']')}"
    count_p1, count_p2 = habit_counts(habit, ctx.today)
    trend = "↗" if count_p1 > count_p2 else "↘" if count_p1 < count_p2 else "→"
    notes_marker = f" {dim('»')}" if habit.id in ctx.noted_ids else ""
    if habit.id in checked_ids:
        label = f"{gray(habit.content.lower())}{tags_str}"
        lines = [f"{indent}{purple('●')} {gray(trend)} {label}{id_str}{notes_marker}"]
    else:
        label = f"{habit.content.lower()}{tags_str}"
        lines = [f"{indent}{purple('○')} {gray(trend)} {label}{id_str}{notes_marker}"]
    for sub in get_subhabits(habit.id):
        lines.extend(row_habit(sub, checked_ids, ctx, indent="   └ "))
    return lines


def row_vice(habit: Habit, checked_ids: set[str], ctx: RenderCtx) -> list[str]:
    id_str = f" {dim('[' + habit.id[:8] + ']')}"
    count_p1, count_p2 = habit_counts(habit, ctx.today)
    if count_p1 > count_p2:
        trend_str = red("↗")
    elif count_p1 < count_p2:
        trend_str = green("↘")
    else:
        trend_str = gray("→")
    if habit.id in checked_ids:
        label = f"{red(habit.content.lower())}"
        lines = [f"  {red('●')} {trend_str} {label}{id_str}"]
    else:
        label = f"{gray(habit.content.lower())}"
        lines = [f"  {green('○')} {trend_str} {label}{id_str}"]
    return lines


def row_daily_habit(habit: Habit, checked_ids: set[str], ctx: RenderCtx) -> list[str]:
    tags_str = fmt_tags(habit.tags, ctx.tag_colors)
    id_str = f" {dim('[' + habit.id[:8] + ']')}"
    count_p1, count_p2 = habit_counts(habit, ctx.today)
    trend = "↗" if count_p1 > count_p2 else "↘" if count_p1 < count_p2 else "→"

    is_checked = habit.id in checked_ids
    notes_marker = f" {dim('»')}" if habit.id in ctx.noted_ids else ""

    if is_checked:
        label = f"{gray(habit.content.lower())}{tags_str}"
        lines = [f"  {purple('●')} {gray(trend)} {label}{id_str}{notes_marker}"]
    else:
        label = f"{habit.content.lower()}{tags_str}"
        lines = [f"  {purple('○')} {gray(trend)} {label}{id_str}{notes_marker}"]
    for sub in get_subhabits(habit.id):
        lines.extend(row_daily_habit(sub, checked_ids, ctx))
    return lines


def habit_sort_key(h: Habit) -> str:
    return h.content.lower()

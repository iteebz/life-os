"""Dashboard section renderers — compose rows into labeled blocks."""

from datetime import date, timedelta

from life.core.models import Habit, Task
from life.lib import clock
from life.lib.ansi import bold, dim, gold, gray, green, purple, red, theme, white
from life.lib.format import fmt_time
from life.lib.tags import load_tag_groups
from life.task import task_sort_key
from life.task.rows import (
    RenderCtx,
    fmt_tags,
    get_tag_order,
    habit_sort_key,
    primary_tag,
    row_daily_habit,
    row_habit,
    row_task,
    row_vice,
)

_R = theme.reset
_GREY = theme.muted

_HABIT_CATEGORY_TAGS = {"self", "love", "admin", "input", "chore", "vice", "hobby"}

_EVENT_EMOJI: dict[str, str] = {
    "birthday": "🎂",
    "anniversary": "💍",
    "deadline": "⚠️",
    "other": "📌",
}


def section_header(
    today: date, tasks_done: int, habits_done: int, total_habits: int, added: int, deleted: int
) -> list[str]:
    time_str = fmt_time(clock.now())
    header = today.strftime("%a") + " · " + today.strftime("%-d %b %Y") + " · " + time_str
    lines = [f"\n{bold(white(header))}"]
    lines.append(f"{_GREY}tasks:{_R} {green(str(tasks_done))}")
    lines.append(f"{_GREY}habits:{_R} {purple(str(habits_done))}")
    if added:
        lines.append(f"{_GREY}added:{_R} {gold(str(added))}")
    if deleted:
        lines.append(f"{_GREY}removed:{_R} {red(str(deleted))}")
    return lines


def section_done(
    items: list[Task | Habit],
    ctx: RenderCtx,
    target_date: date | None = None,
    show_header: bool = True,
) -> list[str]:
    if not items:
        return []
    target = target_date or ctx.today

    def _sort_key(item: Task | Habit):
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
        tags_str = fmt_tags(item.tags, ctx.tag_colors)
        content = item.content.lower()
        id_str = f" {dim('[' + item.id[:8] + ']')}"
        if isinstance(item, Habit):
            on_date = [c for c in item.checks if c.date() == target]
            time_str = fmt_time(max(on_date)) if on_date else ""
            lines.append(f"  {purple('●')} {_GREY}{time_str}{_R} {content}{tags_str}{id_str}")
        elif item.completed_at:
            time_str = fmt_time(item.completed_at)
            parent_str = ""
            if item.parent_id:
                parent = next((t for t in ctx.pending if t.id == item.parent_id), None)
                if parent and not parent.completed_at:
                    parent_str = f" {dim('→ ' + parent.content.lower())}"
            lines.append(f"  {green('✓')} {_GREY}{time_str}{_R} {content}{tags_str}{id_str}{parent_str}")
    return lines


def section_overdue(tasks: list[Task], ctx: RenderCtx) -> tuple[list[str], set[str]]:
    lines = [f"\n{theme.bold}{theme.red}OVERDUE{_R}"]
    scheduled_ids: set[str] = set()
    for task in sorted(tasks, key=task_sort_key):
        scheduled_ids.add(task.id)
        lines.extend(row_task(task, ctx, {}))
        for sub in ctx.subtasks.get(task.id, []):
            scheduled_ids.add(sub.id)
    return lines, scheduled_ids


def section_schedule(
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
        lines.extend(row_task(task, ctx, {}, show_date=False, show_parent=True))
        for sub in ctx.subtasks.get(task.id, []):
            scheduled_ids.add(sub.id)

    for event in all_events:
        emoji = _EVENT_EMOJI.get(str(event.get("type", "")), "📌")
        lines.append(f"  {emoji} {str(event.get('name', '')).lower()}")

    return lines, scheduled_ids


def section_daily(habits: list[Habit], checked_ids: set[str], ctx: RenderCtx) -> list[str]:
    matching = [
        h
        for h in habits
        if not h.private
        and not h.parent_id
        and "self" in (h.tags or [])
        and "vice" not in (h.tags or [])
        and h.cadence != "weekly"
    ]
    if not matching:
        return []
    done_count = sum(1 for h in matching if h.id in checked_ids)
    lines = [f"\n{theme.bold}{theme.purple}DAILY ({done_count}/{len(matching)}){_R}"]
    remaining = [h for h in matching if h.id not in checked_ids]
    done = [h for h in matching if h.id in checked_ids]

    def _daily_sort(h: Habit) -> tuple[int, str]:
        return (0 if h.scheduled_time else 1, h.scheduled_time or h.content.lower())

    if remaining or done:
        for habit in sorted(remaining, key=_daily_sort) + sorted(done, key=_daily_sort):
            lines.extend(row_daily_habit(habit, checked_ids, ctx))
    else:
        lines.append(f"  {gray('all done.')}")
    return lines


def tag_section(
    habits: list[Habit],
    checked_ids: set[str],
    ctx: RenderCtx,
    tag: str,
    label: str,
    color: str,
) -> list[str]:
    matching = [
        h
        for h in habits
        if not h.private
        and not h.parent_id
        and tag in (h.tags or [])
        and "vice" not in (h.tags or [])
        and h.cadence != "weekly"
    ]
    if not matching:
        return []
    done_count = sum(1 for h in matching if h.id in checked_ids)
    lines = [f"\n{theme.bold}{color}{label} ({done_count}/{len(matching)}){_R}"]
    remaining = [h for h in matching if h.id not in checked_ids]
    if remaining:
        for habit in sorted(remaining, key=habit_sort_key):
            lines.extend(row_habit(habit, checked_ids, ctx))
    else:
        lines.append(f"  {gray('all done.')}")
    return lines


def section_hobbies(habits: list[Habit], checked_ids: set[str], ctx: RenderCtx) -> list[str]:
    week_start = ctx.today - timedelta(days=ctx.today.weekday())

    def _is_done(h: Habit) -> bool:
        if h.id in checked_ids:
            return True
        if h.cadence == "weekly":
            return any(week_start <= dt.date() <= ctx.today for dt in h.checks)
        return False

    matching = [
        h
        for h in habits
        if not h.private and not h.parent_id and "hobby" in (h.tags or []) and "vice" not in (h.tags or [])
    ]
    if not matching:
        return []
    daily = [h for h in matching if h.cadence != "weekly"]
    weekly = [h for h in matching if h.cadence == "weekly"]
    done_count = sum(1 for h in daily if h.id in checked_ids) + sum(1 for h in weekly if _is_done(h))
    total = len(matching)
    lines = [f"\n{theme.bold}{theme.green}HOBBIES ({done_count}/{total}){_R}"]
    remaining = [h for h in matching if not _is_done(h)]
    if remaining:
        for habit in sorted(remaining, key=habit_sort_key):
            lines.extend(row_habit(habit, checked_ids, ctx))
    else:
        lines.append(f"  {gray('all done.')}")
    return lines


def section_weekly(habits: list[Habit], checked_ids: set[str], ctx: RenderCtx) -> list[str]:
    week_start = ctx.today - timedelta(days=ctx.today.weekday())

    def _is_done(h: Habit) -> bool:
        if h.id in checked_ids:
            return True
        return any(week_start <= dt.date() <= ctx.today for dt in h.checks)

    weekly = [
        h
        for h in habits
        if not h.private and not h.parent_id and h.cadence == "weekly" and "hobby" not in (h.tags or [])
    ]
    if not weekly:
        return []
    lines = [f"\n{theme.bold}{theme.purple}WEEKLY{_R}"]
    remaining = [h for h in weekly if not _is_done(h)]
    if remaining:
        for habit in sorted(remaining, key=habit_sort_key):
            lines.extend(row_habit(habit, checked_ids, ctx))
    else:
        lines.append(f"  {gray('all done.')}")
    return lines


def section_untagged(habits: list[Habit], checked_ids: set[str], ctx: RenderCtx) -> list[str]:
    residual = [
        h
        for h in habits
        if not h.private
        and not h.parent_id
        and h.cadence != "weekly"
        and not (set(h.tags or []) & _HABIT_CATEGORY_TAGS)
    ]
    if not residual:
        return []
    done_count = sum(1 for h in residual if h.id in checked_ids)
    lines = [f"\n{theme.bold}{theme.purple}HABITS ({done_count}/{len(residual)}){_R}"]
    remaining = [h for h in residual if h.id not in checked_ids]
    for habit in sorted(remaining, key=habit_sort_key):
        lines.extend(row_habit(habit, checked_ids, ctx))
    return lines


def section_vices(habits: list[Habit], checked_ids: set[str], ctx: RenderCtx) -> list[str]:
    vices = [h for h in habits if not h.private and not h.parent_id and "vice" in (h.tags or [])]
    if not vices:
        return []
    clean_count = sum(1 for h in vices if h.id not in checked_ids)
    lines = [f"\n{theme.bold}{theme.red}VICES ({clean_count}/{len(vices)}){_R}"]
    clean = sorted([h for h in vices if h.id not in checked_ids], key=lambda h: h.content.lower())
    used = sorted([h for h in vices if h.id in checked_ids], key=lambda h: h.content.lower())
    for vice in clean + used:
        lines.extend(row_vice(vice, checked_ids, ctx))
    return lines


def section_backlog(
    tasks: list[Task],
    ctx: RenderCtx,
    completed_subs: dict[str, list[Task]],
) -> list[str]:
    if not tasks:
        return []
    groups: dict[str, list[Task]] = {}
    for task in sorted(tasks, key=lambda t: t.content.lower()):
        groups.setdefault(primary_tag(task) or "", []).append(task)

    tag_order = get_tag_order()
    tag_labels = dict(load_tag_groups())

    # tags.toml [groups] is the viability contract — unknown tags collapse into OTHER
    known = set(tag_order)
    other: list[Task] = []
    for tag in list(groups):
        if tag and tag not in known:
            other.extend(groups.pop(tag))
    if "" in groups:
        other.extend(groups.pop(""))
    if other:
        groups[""] = sorted(other, key=lambda t: t.content.lower())

    sections = [t for t in tag_order if t in groups]
    if "" in groups:
        sections.append("")

    lines: list[str] = []
    for tag in sections:
        label = tag_labels.get(tag, tag.upper()) if tag else "OTHER"
        color = ctx.tag_colors.get(tag, theme.white) if tag else theme.white
        lines.append(f"\n{theme.bold}{color}{label} ({len(groups[tag])}){_R}")
        for task in groups[tag]:
            lines.extend(row_task(task, ctx, completed_subs, tags_override=task.tags))
    return lines

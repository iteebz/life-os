"""Dashboard section renderers — compose rows into labeled blocks."""

from datetime import date, timedelta

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
from lifeos.core.lib import clock
from lifeos.core.lib.ansi import bold, dim, gold, gray, green, purple, red, theme, white
from lifeos.core.lib.format import fmt_time
from lifeos.core.lib.tags import load_tag_groups
from lifeos.core.models import Habit, Task

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
    lines.append(f"{_GREY}done:{_R} {green(str(tasks_done))}{_GREY}+{_R}{purple(str(habits_done))}")
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


def _pad_hm(t: str) -> str:
    """Zero-pad H:MM → HH:MM for stable lexicographic sort."""
    if ":" in t and len(t.split(":", 1)[0]) == 1:
        return "0" + t
    return t


def section_done_today(
    ctx: RenderCtx,
    today_items: list[Task | Habit],
    all_habits: list[Habit],
    checked_ids: set[str],
    due_today_ids: set[str],
) -> list[str]:
    """Chronological log of what got done today — tasks completed + habits checked."""
    now_time = clock.now().strftime("%H:%M")
    entries: list[tuple[str, list[str]]] = []

    for task in (i for i in today_items if isinstance(i, Task) and i.completed_at):
        if task.id in due_today_ids:
            continue
        t_sort = task.completed_at.strftime("%H:%M")  # type: ignore[union-attr]
        t_disp = fmt_time(task.completed_at)  # type: ignore[union-attr]
        tags_str = fmt_tags(task.tags, ctx.tag_colors)
        id_str = f" {dim('[' + task.id[:8] + ']')}"
        notes_marker = f" {dim('»')}" if task.id in ctx.noted_ids else ""
        entries.append(
            (t_sort, [f"  {green('✓')} {gray(t_disp)} {task.content.lower()}{tags_str}{id_str}{notes_marker}"])
        )

    for habit in all_habits:
        if habit.private or habit.parent_id or "vice" in (habit.tags or []) or habit.id not in checked_ids:
            continue
        day_checks = [c for c in habit.checks if c.date() == ctx.today]
        check_dt = max(day_checks) if day_checks else None
        t_str = check_dt.strftime("%H:%M") if check_dt else now_time
        t_disp = fmt_time(check_dt) if check_dt else now_time
        tags_str = fmt_tags(habit.tags, ctx.tag_colors)
        id_str = f" {dim('[' + habit.id[:8] + ']')}"
        notes_marker = f" {dim('»')}" if habit.id in ctx.noted_ids else ""
        row = f"  {purple('●')} {gray(t_disp)} {habit.content.lower()}{tags_str}{id_str}{notes_marker}"
        entries.append((_pad_hm(t_str), [row]))

    if not entries:
        return []

    entries.sort(key=lambda x: x[0])
    task_count = sum(1 for i in today_items if isinstance(i, Task) and i.completed_at and i.id not in due_today_ids)
    habit_count = len(entries) - task_count
    lines = [f"\n{bold(green(f'DONE ({task_count}+{habit_count})'))}"]
    for _, rows in entries:
        lines.extend(rows)
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

    if remaining or done:
        for habit in sorted(remaining, key=lambda h: h.content.lower()) + sorted(done, key=lambda h: h.content.lower()):
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


def section_habit_summary(habits: list[Habit], checked_ids: set[str], ctx: RenderCtx) -> list[str]:
    """Single compact summary line replacing all habit sections."""
    week_start = ctx.today - timedelta(days=ctx.today.weekday())

    def _done(h: Habit) -> bool:
        if h.id in checked_ids:
            return True
        if h.cadence == "weekly":
            return any(week_start <= dt.date() <= ctx.today for dt in h.checks)
        return False

    categories: list[tuple[str, str, list[str]]] = [
        ("love", theme.pink, []),
        ("admin", theme.yellow, []),
        ("chore", theme.cyan, []),
        ("hobby", theme.green, []),
        ("hygiene", theme.purple, []),
        ("health", theme.green, []),
    ]
    cat_tags = {tag for tag, _, _ in categories}

    buckets: dict[str, list[Habit]] = {tag: [] for tag, _, _ in categories}
    other: list[Habit] = []

    for h in habits:
        if h.private or h.parent_id or "vice" in (h.tags or []):
            continue
        tags = set(h.tags or [])
        matched = False
        for tag, _, _ in categories:
            if tag in tags:
                buckets[tag].append(h)
                matched = True
                break
        if not matched and not (tags & cat_tags):
            other.append(h)

    parts: list[str] = []
    for tag, color, _ in categories:
        bucket = buckets[tag]
        if not bucket:
            continue
        done = sum(1 for h in bucket if _done(h))
        parts.append(f"{color}{tag} {done}/{len(bucket)}{_R}")

    if other:
        done = sum(1 for h in other if _done(h))
        parts.append(f"{theme.purple}other {done}/{len(other)}{_R}")

    if not parts:
        return []

    total = sum(len(b) for b in buckets.values()) + len(other)
    total_done = sum(sum(1 for h in b if _done(h)) for b in buckets.values()) + sum(1 for h in other if _done(h))
    header = f"{theme.bold}{theme.purple}HABITS ({total_done}/{total}){_R}"
    sep = gray(" · ")
    return [f"\n{header}  {sep.join(parts)}"]


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

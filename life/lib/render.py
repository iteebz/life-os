from collections.abc import Sequence
from datetime import date, timedelta

from life.habits import get_subhabits
from life.models import Habit, Task, TaskMutation
from life.tasks import _task_sort_key

from . import clock
from .ansi import ANSI, bold, coral, cyan, dim, gold, gray, green, red, white
from .format import format_habit, format_task

__all__ = [
    "render_dashboard",
    "render_habit_matrix",
    "render_item_list",
    "render_momentum",
    "render_task_detail",
]

_R = ANSI.RESET
_GREY = ANSI.MUTED


def _fmt_time(t: str) -> str:
    return f"{ANSI.SECONDARY}{t}{_R}"


def _fmt_rel_date(
    due: date, today: date, time: str | None = None, is_deadline: bool = False
) -> str:
    delta = (due - today).days
    if delta <= 7:
        day_label = due.strftime("%a").lower()
        label = f"{day_label}·{time}" if time else day_label
    else:
        label = f"+{delta}d"
    return coral(label) if is_deadline else label


def _fmt_tags(tags: list[str], tag_colors: dict[str, str]) -> str:
    if not tags:
        return ""
    parts = [f"{tag_colors.get(t, _GREY)}#{t}{_R}" for t in tags]
    return " " + " ".join(parts)


def _get_direct_tags(task: Task, all_pending: list[Task]) -> list[str]:
    if not task.parent_id:
        return task.tags

    parent = next((t for t in all_pending if t.id == task.parent_id), None)
    if not parent:
        return task.tags

    parent_tags = parent.tags
    return [tag for tag in task.tags if tag not in parent_tags]


def _build_tag_colors(items: Sequence[Task | Habit]) -> dict[str, str]:
    tags = sorted({tag for item in items for tag in item.tags})
    return {tag: ANSI.POOL[i % len(ANSI.POOL)] for i, tag in enumerate(tags)}


def _get_trend(current: int, previous: int) -> str:
    if previous == 0:
        return "↗" if current > 0 else "→"
    if current > previous:
        return "↗"
    if current < previous:
        return "↘"
    return "→"


def _render_subtask_row(
    sub: Task,
    all_pending: list[Task],
    tag_colors: dict[str, str],
    indent: str = "    └ ",
) -> str:
    sub_id_str = f" {_GREY}[{sub.id[:8]}]{_R}"
    sub_direct_tags = _get_direct_tags(sub, all_pending)
    sub_tags_str = _fmt_tags(sub_direct_tags, tag_colors)
    if sub.scheduled_date and sub.scheduled_date == clock.today():
        now_str = clock.now().strftime("%H:%M")
        sub_time_str = f"{bold(white(f'TODAY · {now_str}'))} "
    elif sub.scheduled_time:
        sub_time_str = f"{_fmt_time(sub.scheduled_time)} "
    else:
        sub_time_str = ""
    return f"{indent}{sub_time_str}{sub.content.lower()}{sub_tags_str}{sub_id_str}{_R}"


def _render_header(
    today: date, tasks_done: int, habits_done: int, total_habits: int, added: int, deleted: int
) -> list[str]:
    lines = [f"\n{bold(white(today.strftime('%a') + ' · ' + today.strftime('%-d %b %Y')))}"]
    lines.append(f"{_GREY}done:{_R} {green(str(tasks_done))}")
    lines.append(f"{_GREY}habits:{_R} {cyan(str(habits_done))}{_GREY}/{total_habits}{_R}")
    if added:
        lines.append(f"{_GREY}added:{_R} {gold(str(added))}")
    if deleted:
        lines.append(f"{_GREY}deleted:{_R} {red(str(deleted))}")
    return lines


def _render_done(
    today_items: list[Task | Habit],
    all_pending: list[Task],
    tag_colors: dict[str, str],
) -> list[str]:
    if not today_items:
        return []

    def _sort_key(item):
        if isinstance(item, Task) and item.completed_at:
            return item.completed_at
        if isinstance(item, Habit) and item.checks:
            return max(item.checks)
        return item.created

    sorted_items = sorted(today_items, key=_sort_key)
    pending_by_id = {t.id: t for t in all_pending}

    lines = [bold(green("DONE"))]
    for item in sorted_items:
        tags_str = _fmt_tags(item.tags, tag_colors)
        content = item.content.lower()
        id_str = f" {_GREY}[{item.id[:8]}]{_R}"
        if isinstance(item, Habit):
            time_str = ""
            if item.checks:
                latest_check = max(item.checks)
                if latest_check.date() == clock.today():
                    time_str = latest_check.strftime("%H:%M")
            lines.append(f"  {gray('✓')} {_GREY}{time_str}{_R} {content}{tags_str}{id_str}")
        elif item.completed_at:
            time_str = item.completed_at.strftime("%H:%M")
            parent_str = ""
            if item.parent_id:
                parent = pending_by_id.get(item.parent_id)
                if parent and not parent.completed_at:
                    parent_str = f" {dim('→ ' + parent.content.lower())}"
            lines.append(
                f"  {green('✓')} {_GREY}{time_str}{_R} {content}{tags_str}{id_str}{parent_str}"
            )
    return lines


def _render_upcoming_dates(today: date) -> list[str]:
    from life.lib.dates import upcoming_dates

    try:
        upcoming = upcoming_dates(within_days=14)
    except Exception:
        return []
    if not upcoming:
        return []
    lines = []
    type_emoji = {"birthday": "🎂", "anniversary": "💍", "deadline": "⚠️", "other": "📌"}
    for d in upcoming:
        emoji = type_emoji.get(d["type"], "📌")
        days = d["days_until"]
        days_str = "today!" if days == 0 else f"in {days}d"
        lines.append(f"{emoji} {d['name']} — {days_str}")
    return lines


def _render_today_tasks(
    due_today: list[Task],
    tag_colors: dict[str, str],
    task_id_to_content: dict[str, str],
    subtasks_by_parent: dict[str, list[Task]],
    all_pending: list[Task],
) -> tuple[list[str], set[str]]:
    now = clock.now()
    lines = [f"\n{bold(white('TODAY · ' + now.strftime('%H:%M')))}"]
    scheduled_ids: set[str] = set()

    if not due_today:
        lines.append(f"  {gray('nothing scheduled.')}")
        return lines, scheduled_ids

    def _sort_key(task: Task):
        if task.scheduled_time:
            return (0, task.scheduled_time, not task.focus)
        return (1, "", not task.focus)

    sorted_today = sorted(due_today, key=_sort_key)

    for task in sorted_today:
        scheduled_ids.add(task.id)
        tags_str = _fmt_tags(task.tags, tag_colors)
        id_str = f" {_GREY}[{task.id[:8]}]{_R}"
        time_str = f"{_fmt_time(task.scheduled_time)} " if task.scheduled_time else ""

        if task.blocked_by:
            blocker = task_id_to_content.get(task.blocked_by, task.blocked_by[:8])
            blocked_str = f" {dim('← ' + blocker.lower())}"
            lines.append(
                f"  ⊘ {time_str}{_GREY}{task.content.lower()}{_R}{tags_str}{blocked_str}{id_str}"
            )
        else:
            fire = f" {ANSI.BOLD}🔥{_R}" if task.focus else ""
            lines.append(f"  □ {time_str}{task.content.lower()}{tags_str}{fire}{id_str}")

        for sub in sorted(subtasks_by_parent.get(task.id, []), key=_task_sort_key):
            scheduled_ids.add(sub.id)
            lines.append(_render_subtask_row(sub, all_pending, tag_colors))

    return lines, scheduled_ids


def _render_day_tasks(
    due_day: list[Task],
    label: str,
    tag_colors: dict[str, str],
    subtasks_by_parent: dict[str, list[Task]],
    all_pending: list[Task],
) -> tuple[list[str], set[str]]:
    if not due_day:
        return [], set()

    lines = [f"\n{bold(white(label))}"]
    scheduled_ids: set[str] = set()

    display_entries: list[tuple[str, Task, Task | None]] = []
    for task in due_day:
        scheduled_ids.add(task.id)
        subs = subtasks_by_parent.get(task.id, [])
        if subs:
            for sub in subs:
                scheduled_ids.add(sub.id)
                display_entries.append((sub.scheduled_time or "ZZZ", sub, task))
        else:
            display_entries.append((task.scheduled_time or "ZZZ", task, None))

    display_entries.sort(key=lambda x: (x[0], x[1].created))

    for _, task, parent in display_entries:
        tags = _get_direct_tags(task, all_pending) if parent else task.tags
        tags_str = _fmt_tags(tags, tag_colors)
        id_str = f" {_GREY}[{task.id[:8]}]{_R}"
        time_str = f"{_fmt_time(task.scheduled_time)} " if task.scheduled_time else ""
        is_focused = task.focus or (parent and parent.focus)
        fire = f" {ANSI.BOLD}🔥{_R}" if is_focused else ""
        if parent:
            parent_hint = f" {dim('~ ' + parent.content.lower())}"
            lines.append(
                f"  □ {time_str}{task.content.lower()}{tags_str}{fire}{parent_hint}{id_str}"
            )
        else:
            lines.append(f"  □ {time_str}{task.content.lower()}{tags_str}{fire}{id_str}")

    return lines, scheduled_ids


def _render_habit_row(
    habit: Habit,
    today_habit_ids: set[str],
    tag_colors: dict[str, str],
    indent: str = "  ",
) -> list[str]:
    tags_str = _fmt_tags(habit.tags, tag_colors)
    today = clock.today()
    p1_start = today - timedelta(days=6)
    p2_start = today - timedelta(days=13)
    p2_end = p1_start - timedelta(days=1)
    count_p1 = sum(1 for dt in habit.checks if p1_start <= dt.date() <= today)
    count_p2 = sum(1 for dt in habit.checks if p2_start <= dt.date() <= p2_end)
    trend = "↗" if count_p1 > count_p2 else "↘" if count_p1 < count_p2 else "→"
    id_str = f" {_GREY}[{habit.id[:8]}]{_R}"
    lines = []
    if habit.id in today_habit_ids:
        lines.append(
            f"{indent}{gray('✓ ' + trend + ' ' + habit.content.lower())}{tags_str}{id_str}"
        )
    else:
        lines.append(f"{indent}□ {trend} {habit.content.lower()}{tags_str}{id_str}")
    for sub in get_subhabits(habit.id):
        lines.extend(_render_habit_row(sub, today_habit_ids, tag_colors, indent="    └ "))
    return lines


def _render_habits(
    habits: list[Habit], today_habit_ids: set[str], tag_colors: dict[str, str]
) -> list[str]:
    visible = [h for h in habits if not h.private and not h.parent_id]
    if not visible:
        return []

    checked_count = sum(1 for h in habits if h.id in today_habit_ids)
    total = len(habits)
    lines = [f"\n{bold(white(f'HABITS ({checked_count}/{total})'))}"]
    sorted_habits = sorted(visible, key=lambda x: x.content.lower())
    unchecked = [h for h in sorted_habits if h.id not in today_habit_ids]
    checked = [h for h in sorted_habits if h.id in today_habit_ids]
    for habit in unchecked + checked:
        lines.extend(_render_habit_row(habit, today_habit_ids, tag_colors))

    return lines


def _render_overdue(
    overdue: list[Task],
    today: date,
    tag_colors: dict[str, str],
    subtasks_by_parent: dict[str, list[Task]],
    all_pending: list[Task],
) -> tuple[list[str], set[str]]:
    lines = [f"\n{ANSI.BOLD}{ANSI.RED}OVERDUE{_R}"]
    scheduled_ids: set[str] = set()
    for task in sorted(overdue, key=_task_sort_key):
        scheduled_ids.add(task.id)
        tags_str = _fmt_tags(task.tags, tag_colors)
        id_str = f" {_GREY}[{task.id[:8]}]{_R}"
        fire = f" {ANSI.BOLD}🔥{_R}" if task.focus else ""
        label = _fmt_rel_date(
            task.scheduled_date or today, today, task.scheduled_time, task.is_deadline
        )
        lines.append(f"  □ {label} {task.content.lower()}{tags_str}{fire}{id_str}")
        for sub in sorted(subtasks_by_parent.get(task.id, []), key=_task_sort_key):
            scheduled_ids.add(sub.id)
            lines.append(_render_subtask_row(sub, all_pending, tag_colors))
    return lines, scheduled_ids


def _render_task_row(
    task: Task,
    today: date,
    today_str: str,
    tomorrow_str: str,
    tag_colors: dict[str, str],
    task_id_to_content: dict[str, str],
    subtasks_by_parent: dict[str, list[Task]],
    completed_subs_by_parent: dict[str, list[Task]],
    all_pending: list[Task],
    indent: str = "  ",
) -> list[str]:
    tags_str = _fmt_tags(task.tags, tag_colors)
    id_str = f" {_GREY}[{task.id[:8]}]{_R}"

    date_str = ""
    if task.scheduled_date and task.scheduled_date.isoformat() not in (today_str, tomorrow_str):
        label = _fmt_rel_date(
            task.scheduled_date or today, today, task.scheduled_time, task.is_deadline
        )
        date_str = f"{label} "

    if task.blocked_by:
        blocker = task_id_to_content.get(task.blocked_by, task.blocked_by[:8])
        blocked_str = f" {dim('← ' + blocker.lower())}"
        row = (
            f"{indent}⊘ {_GREY}{date_str}{task.content.lower()}{tags_str}{_R}{blocked_str}{id_str}"
        )
    else:
        indicator = f"{ANSI.BOLD}🔥{_R} " if task.focus else ""
        row = f"{indent}{indicator}{date_str}{task.content.lower()}{tags_str}{id_str}"

    rows = [row]
    rows.extend(
        _render_subtask_row(sub, all_pending, tag_colors, indent=f"{indent}  └ ")
        for sub in sorted(subtasks_by_parent.get(task.id, []), key=_task_sort_key)
    )
    for sub in completed_subs_by_parent.get(task.id, []):
        sub_direct_tags = _get_direct_tags(sub, all_pending)
        sub_tags_str = _fmt_tags(sub_direct_tags, tag_colors)
        sub_time_str = f"{_fmt_time(sub.scheduled_time)} " if sub.scheduled_time else ""
        rows.append(
            f"{indent}  {gray('└ ' + sub_time_str + '✓ ' + sub.content.lower())}{sub_tags_str}{id_str}"
        )
    return rows


def _render_tasks(
    regular_items: list[Task],
    today: date,
    today_str: str,
    tomorrow_str: str,
    tag_colors: dict[str, str],
    task_id_to_content: dict[str, str],
    subtasks_by_parent: dict[str, list[Task]],
    completed_subs_by_parent: dict[str, list[Task]],
    all_pending: list[Task],
) -> list[str]:
    if not regular_items:
        return []

    subtask_ids = {t.id for t in regular_items if t.parent_id}
    top_level = [t for t in regular_items if t.id not in subtask_ids]
    lines_out: list[str] = [f"\n{bold(white(f'TASKS ({len(top_level)})'))}"]

    lines: list[str] = []
    seen: set[str] = set()
    for task in sorted(top_level, key=lambda t: t.content.lower()):
        if task.id in seen:
            continue
        seen.add(task.id)
        lines.extend(
            _render_task_row(
                task,
                today,
                today_str,
                tomorrow_str,
                tag_colors,
                task_id_to_content,
                subtasks_by_parent,
                completed_subs_by_parent,
                all_pending,
            )
        )

    return lines_out + lines


def render_dashboard(
    items, today_breakdown, momentum, context, today_items=None, profile=None, verbose=False
):
    habits_today, tasks_today, added_today, deleted_today = today_breakdown
    today = clock.today()
    today_str = today.isoformat()
    tomorrow = today + timedelta(days=1)
    tomorrow_str = tomorrow.isoformat()

    all_pending = [item for item in items if isinstance(item, Task)]
    all_items = items + (today_items or [])
    tag_colors = _build_tag_colors(all_items)

    lines: list[str] = []

    habits = [item for item in items if isinstance(item, Habit)]
    total_habits = len({h.id for h in habits})
    lines.extend(
        _render_header(today, tasks_today, habits_today, total_habits, added_today, deleted_today)
    )

    done_lines = _render_done(today_items or [], all_pending, tag_colors)
    if done_lines:
        lines.append("")
        lines.extend(done_lines)

    lines.extend(_render_upcoming_dates(today))

    all_subtask_ids = {t.id for t in all_pending if t.parent_id}
    subtasks_by_parent: dict[str, list[Task]] = {}
    for t in all_pending:
        if t.parent_id:
            subtasks_by_parent.setdefault(t.parent_id, []).append(t)

    task_id_to_content = {t.id: t.content for t in all_pending}

    overdue = [
        t
        for t in all_pending
        if t.scheduled_date and t.scheduled_date < today and t.id not in all_subtask_ids
    ]
    scheduled_ids: set[str] = set()
    if overdue:
        overdue_lines, overdue_ids = _render_overdue(
            overdue, today, tag_colors, subtasks_by_parent, all_pending
        )
        lines.extend(overdue_lines)
        scheduled_ids.update(overdue_ids)

    due_today = [
        t
        for t in all_pending
        if t.scheduled_date
        and t.scheduled_date.isoformat() == today_str
        and t.id not in all_subtask_ids
    ]

    today_lines, today_scheduled = _render_today_tasks(
        due_today,
        tag_colors,
        task_id_to_content,
        subtasks_by_parent,
        all_pending,
    )
    scheduled_ids.update(today_scheduled)
    lines.extend(today_lines)

    for offset in range(1, 8):
        day = today + timedelta(days=offset)
        day_str = day.isoformat()
        if offset == 1:
            label = "TOMORROW"
        elif offset <= 7:
            label = day.strftime("%A").upper()
        else:
            label = day_str
        due_day = [
            t
            for t in all_pending
            if t.scheduled_date
            and t.scheduled_date.isoformat() == day_str
            and t.id not in all_subtask_ids
        ]
        day_lines, day_scheduled = _render_day_tasks(
            due_day,
            label,
            tag_colors,
            subtasks_by_parent,
            all_pending,
        )
        scheduled_ids.update(day_scheduled)
        lines.extend(day_lines)

    today_habit_items = [item for item in (today_items or []) if isinstance(item, Habit)]
    today_habit_ids = {item.id for item in today_habit_items}
    all_habits = list(set(habits + today_habit_items))
    lines.extend(_render_habits(all_habits, today_habit_ids, tag_colors))

    regular_items = [
        item for item in items if isinstance(item, Task) and item.id not in scheduled_ids
    ]
    completed_today_tasks = [i for i in (today_items or []) if isinstance(i, Task)]
    completed_subs_by_parent: dict[str, list[Task]] = {}
    for t in completed_today_tasks:
        if t.parent_id:
            completed_subs_by_parent.setdefault(t.parent_id, []).append(t)

    lines.extend(
        _render_tasks(
            regular_items,
            today,
            today_str,
            tomorrow_str,
            tag_colors,
            task_id_to_content,
            subtasks_by_parent,
            completed_subs_by_parent,
            all_pending,
        )
    )

    return "\n".join(lines) + "\n"


def render_momentum(momentum) -> str:
    lines = [f"\n{bold(white('MOMENTUM:'))}"]
    for week_name in ["this_week", "last_week", "prior_week"]:
        week_data = momentum[week_name]
        tasks_c = week_data.tasks_completed
        habits_c = week_data.habits_completed
        tasks_t = week_data.tasks_total
        habits_t = week_data.habits_total

        tasks_rate = (tasks_c / tasks_t) * 100 if tasks_t > 0 else 0
        habits_rate = (habits_c / habits_t) * 100 if habits_t > 0 else 0

        lines.append(f"  {week_name.replace('_', ' ').lower()}:")
        lines.append(f"    tasks: {tasks_c}/{tasks_t} ({tasks_rate:.0f}%)")
        lines.append(f"    habits: {habits_c}/{habits_t} ({habits_rate:.0f}%)")

    if "this_week" in momentum and "last_week" in momentum:
        this_week = momentum["this_week"]
        last_week = momentum["last_week"]

        lines.append(f"\n{bold(white('TRENDS (vs. Last Week):'))}")

        tasks_trend = _get_trend(this_week.tasks_completed, last_week.tasks_completed)
        habits_trend = _get_trend(this_week.habits_completed, last_week.habits_completed)

        lines.append(f"  Tasks: {tasks_trend}")
        lines.append(f"  Habits: {habits_trend}")

    return "\n".join(lines)


def render_item_list(items: list[Task | Habit]):
    if not items:
        return "No pending items."

    lines = []
    for item in items:
        if isinstance(item, Task):
            lines.append(format_task(item, tags=item.tags, show_id=True))
        else:
            lines.append(format_habit(item, tags=item.tags, show_id=True))

    return "\n".join(lines)


def render_habit_matrix(habits: list[Habit]) -> str:
    lines = []
    lines.append("HABIT TRACKER (last 7 days)\n")

    if not habits:
        return "No habits found."

    today = clock.today()
    day_names = [(today - timedelta(days=i)).strftime("%a").lower() for i in range(6, -1, -1)]
    dates = [(today - timedelta(days=i)) for i in range(6, -1, -1)]

    header = "habit           " + " ".join(day_names) + "   key"
    lines.append(header)
    lines.append("-" * len(header))

    sorted_habits = sorted(habits, key=lambda x: x.content.lower())

    for habit in sorted_habits:
        habit_name = habit.content.lower()
        padded_habit_name = f"{habit_name:<15}"

        check_dates = {dt.date() for dt in habit.checks}

        status_indicators = []
        for date_item in dates:
            if date_item in check_dates:
                status_indicators.append("✓")
            else:
                status_indicators.append("□")

        lines.append(
            f"{padded_habit_name} {'   '.join(status_indicators)}   {_GREY}[{habit.id[:8]}]{_R}"
        )

    return "\n".join(lines)


def _render_task_block(
    task: Task,
    subtasks: list[Task],
    all_tasks: list[Task],
    tag_colors: dict[str, str],
    mutations: list[TaskMutation] | None = None,
    indent: str = "",
) -> list[str]:
    lines = []
    tags_str = _fmt_tags(task.tags, tag_colors)
    focus_str = f" {ANSI.BOLD}🔥{_R}" if task.focus else ""
    status = gray("✓") if task.completed_at else "□"
    id_str = f"{dim('[' + task.id[:8] + ']')}"

    lines.append(f"{indent}{status} {id_str}  {task.content.lower()}{tags_str}{focus_str}")

    if task.scheduled_date:
        label = "deadline" if task.is_deadline else "scheduled"
        date_str = task.scheduled_date.isoformat()
        if task.scheduled_time:
            date_str += f" {_fmt_time(task.scheduled_time)}"
        entry = f"{coral(label) if task.is_deadline else label}: {date_str}"
        lines.append(f"{indent}  {entry}")

    if task.description:
        lines.append(f"{indent}  {task.description}")

    if task.blocked_by:
        lines.append(f"{indent}  blocked by: {task.blocked_by[:8]}")

    for sub in sorted(subtasks, key=_task_sort_key):
        sub_status = gray("✓") if sub.completed_at else "□"
        sub_id_str = dim(f"[{sub.id[:8]}]")
        sub_direct_tags = _get_direct_tags(sub, all_tasks)
        sub_tags_str = _fmt_tags(sub_direct_tags, tag_colors)
        sub_time_str = f"{dim(_fmt_time(sub.scheduled_time))} " if sub.scheduled_time else ""
        lines.append(
            f"{indent}  └ {sub_status} {sub_id_str}  {sub_time_str}{sub.content.lower()}{sub_tags_str}"
        )

    deferrals = [m for m in (mutations or []) if m.field == "defer" or m.reason == "overdue_reset"]
    if deferrals:
        lines.append(f"{indent}  deferrals:")
        for m in deferrals:
            when = m.mutated_at.strftime("%Y-%m-%d")
            reason = f" — {m.reason}" if m.reason else ""
            lines.append(f"{indent}    {when}{reason}")

    return lines


def render_task_detail(
    task: Task,
    subtasks: list[Task],
    mutations: list[TaskMutation] | None = None,
    parent: Task | None = None,
    parent_subtasks: list[Task] | None = None,
) -> str:
    all_tasks = [task, *subtasks, *(parent_subtasks or []), *([parent] if parent else [])]
    tag_colors = _build_tag_colors(all_tasks)

    if parent:
        lines = _render_task_block(parent, parent_subtasks or [], all_tasks, tag_colors)
    else:
        lines = _render_task_block(task, subtasks, all_tasks, tag_colors, mutations)

    return "\n".join(lines)

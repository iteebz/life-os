import sys
from datetime import date, datetime

from . import ansi

__all__ = [
    "format_due",
    "format_elapsed",
    "format_habit",
    "format_status",
    "format_task",
    "render_done_row",
    "render_uncheck_row",
]


def format_elapsed(dt: datetime, now: datetime | None = None) -> str:
    """Format a datetime as a human-readable relative string (e.g. '5m ago', '3h ago')."""
    if now is None:
        now = datetime.now()
    s = int((now - dt).total_seconds())
    if s < 60:
        return f"{s}s ago"
    m = s // 60
    if m < 60:
        return f"{m}m ago"
    h = m // 60
    if h < 24:
        return f"{h}h ago"
    d = h // 24
    if d < 7:
        return f"{d}d ago"
    return dt.strftime("%Y-%m-%d")


def render_done_row(
    content: str, time_str: str, tags: list[str], item_id: str, is_habit: bool = False
) -> None:
    r = ansi._active.reset
    grey = ansi._active.muted
    check = ansi.gray("✓") if is_habit else ansi.green("✓")
    tag_str = ""
    if tags:
        parts = [f"{ansi.POOL[hash(t) % len(ansi.POOL)]}#{t}{r}" for t in tags]
        tag_str = " " + " ".join(parts)
    id_str = f" {grey}[{item_id[:8]}]{r}"
    time_part = f"{grey}{time_str}{r} " if time_str else ""
    sys.stdout.write(f"  {check} {time_part}{content}{tag_str}{id_str}\n")
    sys.stdout.flush()


def render_uncheck_row(content: str, tags: list[str], item_id: str) -> None:
    r = ansi._active.reset
    grey = ansi._active.muted
    tag_str = ""
    if tags:
        parts = [f"{ansi.POOL[hash(t) % len(ansi.POOL)]}#{t}{r}" for t in tags]
        tag_str = " " + " ".join(parts)
    id_str = f" {grey}[{item_id[:8]}]{r}"
    sys.stdout.write(f"  □ {content}{tag_str}{id_str}\n")
    sys.stdout.flush()


def _format_tags(tags: list[str]) -> str:
    """Format a list of tags for display."""
    return " ".join(ansi.muted(f"#{tag}") for tag in tags)


def format_due(due_date: date | str, colorize: bool = True) -> str:
    if not due_date:
        return ""

    if isinstance(due_date, str):
        due = date.fromisoformat(due_date)
    else:
        due = due_date

    date_str = due.strftime("%d/%m")

    if colorize:
        return ansi.muted(f"{date_str}·")
    return f"{date_str}·"


def format_task(task, tags: list[str] | None = None, show_id: bool = False) -> str:
    """Format a task for display. Returns: [⦿] [due] content [#tags] [id]"""
    parts = []

    if task.focus:
        parts.append(ansi.bold("⦿"))

    if task.scheduled_date:
        parts.append(format_due(task.scheduled_date, colorize=True))

    parts.append(task.content.lower())

    if tags:
        parts.append(_format_tags(tags))

    if show_id:
        parts.append(ansi.muted(f"[{task.id[:8]}]"))

    return " ".join(parts)


def format_habit(
    habit, checked: bool = False, tags: list[str] | None = None, show_id: bool = False
) -> str:
    """Format a habit for display. Returns: [✓|□] content [#tags] [id]"""
    parts = []

    if checked:
        parts.append(ansi.muted("✓"))
    else:
        parts.append("□")

    parts.append(habit.content.lower())

    if tags:
        parts.append(_format_tags(tags))

    if show_id:
        parts.append(ansi.muted(f"[{habit.id[:8]}]"))

    return " ".join(parts)


def format_status(symbol: str, content: str, item_id: str | None = None) -> str:
    """Format status message for action confirmations."""
    if item_id:
        return f"{symbol} {content} {ansi.muted(f'[{item_id[:8]}]')}"
    return f"{symbol} {content}"

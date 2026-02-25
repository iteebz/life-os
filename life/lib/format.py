import sys
from datetime import date, datetime

from .ansi import ANSI

__all__ = [
    "animate_check",
    "format_due",
    "format_elapsed",
    "format_habit",
    "format_status",
    "format_task",
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


def animate_check(label: str) -> None:
    sys.stdout.write(f"  {ANSI.GREEN}\u2713{ANSI.RESET} {ANSI.GREY}{label}{ANSI.RESET}\n")
    sys.stdout.flush()


def _format_tags(tags: list[str]) -> str:
    """Format a list of tags for display."""
    return " ".join(f"{ANSI.GREY}#{tag}{ANSI.RESET}" for tag in tags)


def format_due(due_date: date | str, colorize: bool = True) -> str:
    if not due_date:
        return ""

    if isinstance(due_date, str):
        due = date.fromisoformat(due_date)
    else:
        due = due_date

    date_str = due.strftime("%d/%m")

    if colorize:
        return f"{ANSI.GREY}{date_str}·{ANSI.RESET}"
    return f"{date_str}·"


def format_task(task, tags: list[str] | None = None, show_id: bool = False) -> str:
    """Format a task for display. Returns: [⦿] [due] content [#tags] [id]"""
    parts = []

    if task.focus:
        parts.append(f"{ANSI.BOLD}⦿{ANSI.RESET}")

    if task.scheduled_date:
        parts.append(format_due(task.scheduled_date, colorize=True))

    parts.append(task.content.lower())

    if tags:
        parts.append(_format_tags(tags))

    if show_id:
        parts.append(f"{ANSI.GREY}[{task.id[:8]}]{ANSI.RESET}")

    return " ".join(parts)


def format_habit(
    habit, checked: bool = False, tags: list[str] | None = None, show_id: bool = False
) -> str:
    """Format a habit for display. Returns: [✓|□] content [#tags] [id]"""
    parts = []

    if checked:
        parts.append(f"{ANSI.GREY}✓{ANSI.RESET}")
    else:
        parts.append("□")

    parts.append(habit.content.lower())

    if tags:
        parts.append(_format_tags(tags))

    if show_id:
        parts.append(f"{ANSI.GREY}[{habit.id[:8]}]{ANSI.RESET}")

    return " ".join(parts)


def format_status(symbol: str, content: str, item_id: str | None = None) -> str:
    """Format status message for action confirmations."""
    if item_id:
        return f"{symbol} {content} {ANSI.GREY}[{item_id[:8]}]{ANSI.RESET}"
    return f"{symbol} {content}"

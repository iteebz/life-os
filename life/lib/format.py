import sys
from datetime import UTC, date, datetime

from . import ansi

__all__ = [
    "format_due",
    "format_elapsed",
    "format_habit",
    "format_status",
    "format_task",
    "render_done_row",
    "render_row",
    "render_uncheck_row",
]


def format_elapsed(dt: datetime, now: datetime | None = None) -> str:
    """Format a datetime as a human-readable relative string (e.g. '5m ago', '3h ago').

    DB timestamps are naive UTC. Normalize both sides to UTC-aware before subtracting.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    if now is None:
        now = datetime.now(UTC)
    elif now.tzinfo is None:
        now = now.astimezone(UTC)
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


def _fmt_tags(tags: list[str]) -> str:
    """Format tags with consistent color-pool coloring (matches dashboard)."""
    if not tags:
        return ""
    r = ansi.theme.reset
    pool = [code for code, _ in ansi.POOL]
    # Deterministic: sorted tag list → stable color assignment
    all_tags = sorted(set(tags))
    colors = {t: pool[i % len(pool)] for i, t in enumerate(all_tags)}
    parts = [f"{colors[t]}#{t}{r}" for t in tags]
    return " " + " ".join(parts)


def render_row(
    content: str,
    tags: list[str],
    item_id: str,
    *,
    symbol: str = "□",
    time_str: str = "",
    prefix: str = "  ",
) -> None:
    """Standardized row renderer. Used by all creation, check, and uncheck paths."""
    r = ansi.theme.reset
    grey = ansi.theme.muted
    tag_str = _fmt_tags(tags)
    id_str = f" {grey}[{item_id[:8]}]{r}"
    time_part = f"{grey}{time_str}{r} " if time_str else ""
    sys.stdout.write(f"{prefix}{symbol} {time_part}{content}{tag_str}{id_str}\n")
    sys.stdout.flush()


def render_done_row(
    content: str, time_str: str, tags: list[str], item_id: str, is_habit: bool = False
) -> None:
    symbol = ansi.purple("●") if is_habit else ansi.green("✓")
    render_row(content, tags, item_id, symbol=symbol, time_str=time_str)


def render_uncheck_row(content: str, tags: list[str], item_id: str, is_habit: bool = False) -> None:
    symbol = ansi.purple("○") if is_habit else "□"
    render_row(content, tags, item_id, symbol=symbol)


def _format_tags(tags: list[str]) -> str:
    """Format tags with consistent color-pool coloring (matches dashboard)."""
    # Strip leading space — _fmt_tags includes it for row context
    return _fmt_tags(tags).lstrip()


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
        parts.append(ansi.purple("●"))
    else:
        parts.append(ansi.purple("○"))

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

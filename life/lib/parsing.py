import re

from .dates import parse_due_date


def validate_content(content: str) -> None:
    """Validate that content is not empty or whitespace-only.

    Raises ValueError if invalid.
    """
    if not content or not content.strip():
        raise ValueError("Content cannot be empty or whitespace-only")


def _try_parse_time(s: str) -> str | None:
    m = re.match(r"^(\d{1,2}):(\d{2})$", s.strip().lower())
    if m:
        h, mn = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mn <= 59:
            return f"{h:02d}:{mn:02d}"
    return None


def parse_due_and_item(args: list[str], remove: bool = False) -> tuple[str | None, str | None, str]:
    """Parse due date, optional time, and item name from variadic args.

    Understands:
      - date tokens: today, tomorrow, day names, YYYY-MM-DD
      - time tokens: HH:MM, 'now'
      - combined: 'today 14:30 task', '14:30 task', 'now task', 'tomorrow task'

    Returns (date_str, time_str, item_name).
    Raises ValueError if parsing fails.
    """
    if not args:
        raise ValueError("Due date and item required")

    date_str: str | None = None
    time_str: str | None = None
    item_args = list(args)

    if remove:
        return None, None, " ".join(item_args)

    from . import clock as _clock

    if item_args and item_args[0].lower() == "now":
        _now = _clock.now()
        date_str = _clock.today().isoformat()
        time_str = _now.strftime("%H:%M")
        item_args = item_args[1:]
    else:
        if item_args:
            parsed_date = parse_due_date(item_args[0])
            if parsed_date:
                date_str = parsed_date
                item_args = item_args[1:]

        if item_args:
            parsed_time = _try_parse_time(item_args[0])
            if parsed_time:
                time_str = parsed_time
                item_args = item_args[1:]
                if not date_str:
                    date_str = _clock.today().isoformat()
            elif not date_str:
                parsed_time2 = _try_parse_time(item_args[0])
                if parsed_time2:
                    time_str = parsed_time2
                    date_str = _clock.today().isoformat()
                    item_args = item_args[1:]

        if not date_str and not time_str and len(item_args) > 1:
            last = item_args[-1]
            if last.lower() == "now":
                _now = _clock.now()
                date_str = _clock.today().isoformat()
                time_str = _now.strftime("%H:%M")
                item_args = item_args[:-1]
            else:
                parsed_date = parse_due_date(last)
                if parsed_date:
                    date_str = parsed_date
                    item_args = item_args[:-1]
                else:
                    parsed_time = _try_parse_time(last)
                    if parsed_time:
                        time_str = parsed_time
                        date_str = _clock.today().isoformat()
                        item_args = item_args[:-1]

    if not item_args:
        raise ValueError("Item name required")

    item_name = " ".join(item_args)
    return date_str, time_str, item_name


def parse_time(time_str: str) -> str:
    time_str = time_str.strip().lower()
    m = re.match(r"^(\d{1,2}):(\d{2})$", time_str)
    if m:
        h, mn = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mn <= 59:
            return f"{h:02d}:{mn:02d}"
    raise ValueError(f"Invalid time '{time_str}' — use HH:MM")


def parse_due_datetime(due_str: str) -> tuple[str | None, str | None]:
    """Parse a combined due string like 'monday 10:00', 'today', 'tomorrow 14:30', 'YYYY-MM-DD'.

    Returns (date_str, time_str). Either may be None.
    """
    parts = due_str.strip().split()
    date_str: str | None = None
    time_str: str | None = None

    if parts:
        date_str = parse_due_date(parts[0])
        if date_str and len(parts) > 1:
            time_str = _try_parse_time(parts[1])
        elif not date_str:
            time_str = _try_parse_time(parts[0])

    return date_str, time_str

import re
from datetime import date, datetime, timedelta
from typing import Any

from dateutil import parser as dateutil_parser
from dateutil.parser import ParserError

from . import clock


def parse_created_date(created_val: int | float | str) -> date:
    """Parse created date from various formats (timestamp, numeric string, ISO string).

    Handles legacy formats: int/float timestamps, numeric strings, ISO date strings.
    """
    if isinstance(created_val, (int, float)):
        return datetime.fromtimestamp(created_val).date()
    if created_val.replace(".", "").isdigit():
        return datetime.fromtimestamp(float(created_val)).date()
    return date.fromisoformat(created_val.split("T")[0])


def parse_due_date(due_str: str) -> str | None:
    """Parses a due date string (e.g., 'today', 'tomorrow', 'mon', 'YYYY-MM-DD')."""
    due_str_lower = due_str.lower()
    today = clock.today()

    if due_str_lower == "today":
        return today.isoformat()
    if due_str_lower == "yesterday":
        return (today - timedelta(days=1)).isoformat()
    if due_str_lower == "tomorrow":
        return (today + timedelta(days=1)).isoformat()
    _day_aliases = {
        "monday": "mon",
        "tuesday": "tue",
        "wednesday": "wed",
        "thursday": "thu",
        "friday": "fri",
        "saturday": "sat",
        "sunday": "sun",
    }
    due_str_lower = _day_aliases.get(due_str_lower, due_str_lower)
    if due_str_lower in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]:
        day_map = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
        current_weekday = today.weekday()
        target_weekday = day_map[due_str_lower]
        days_ahead = (target_weekday - current_weekday + 7) % 7
        if days_ahead == 0 and due_str_lower != today.strftime("%a").lower():
            days_ahead = 7
        return (today + timedelta(days=days_ahead)).isoformat()
    if re.match(r"^\d{1,2}:\d{2}$", due_str.strip()):
        return None
    try:
        return (
            dateutil_parser.parse(due_str, default=datetime(today.year, today.month, today.day))
            .date()
            .isoformat()
        )
    except (ParserError, ValueError, OverflowError):
        return None


def _days_until(month: int, day: int, today: date) -> int:
    """Days until next occurrence of a recurring MM-DD date."""
    this_year = today.replace(month=month, day=day)
    if this_year >= today:
        return (this_year - today).days
    next_year = this_year.replace(year=today.year + 1)
    return (next_year - today).days


def list_dates() -> list[dict[str, Any]]:
    """Get all special dates from DB, sorted by next occurrence."""
    from life import db

    today = clock.today()
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT id, name, month, day, type FROM special_dates ORDER BY name"
        ).fetchall()

    result = []
    for row in rows:
        id_, name, month, day, type_ = row
        days = _days_until(month, day, today)
        result.append(
            {"id": id_, "name": name, "month": month, "day": day, "type": type_, "days_until": days}
        )

    return sorted(result, key=lambda x: x["days_until"])


def add_date(name: str, date_str: str, type_: str = "other") -> None:
    """Add a special date to DB. date_str is DD-MM."""
    from life import db

    parts = date_str.split("-")
    if len(parts) != 2:
        raise ValueError(f"Invalid date format '{date_str}' — use DD-MM")
    try:
        day, month = int(parts[0]), int(parts[1])
    except ValueError:
        raise ValueError(f"Invalid date format '{date_str}' — use DD-MM") from None
    if not (1 <= month <= 12) or not (1 <= day <= 31):
        raise ValueError(f"Invalid date '{date_str}'")

    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO special_dates (name, month, day, type) VALUES (?, ?, ?, ?)",
            (name, month, day, type_),
        )


def remove_date(name: str) -> None:
    """Remove a special date by name."""
    from life import db

    with db.get_db() as conn:
        conn.execute("DELETE FROM special_dates WHERE name = ?", (name,))


def upcoming_dates(within_days: int = 14) -> list[dict[str, Any]]:
    """Get dates occurring within the next N days."""
    return [d for d in list_dates() if d["days_until"] <= within_days]

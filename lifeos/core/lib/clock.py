"""Centralized accessors for time-related values."""

from datetime import date, datetime

_QUIET_END = 6  # 6am
_QUIET_START = 24  # no evening quiet window


def today() -> date:
    return date.today()


def now() -> datetime:
    return datetime.now()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def is_quiet_now() -> bool:
    """True between midnight and 6am — daemon should not send unsolicited messages."""
    h = datetime.now().hour
    return h < _QUIET_END or h >= _QUIET_START

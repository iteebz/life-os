"""Centralized accessors for time-related values."""

from datetime import date as _date
from datetime import datetime as _datetime

_QUIET_END = 6   # 6am
_QUIET_START = 24  # no evening quiet window


def today() -> _date:
    return _date.today()


def now() -> _datetime:
    return _datetime.now()


def now_iso() -> str:
    return _datetime.now().isoformat(timespec="seconds")


def is_quiet_now() -> bool:
    """True between midnight and 6am — daemon should not send unsolicited messages."""
    h = _datetime.now().hour
    return h < _QUIET_END or h >= _QUIET_START

"""Centralized accessors for time-related values."""

from datetime import date as _date
from datetime import datetime as _datetime


def today() -> _date:
    return _date.today()


def now() -> _datetime:
    return _datetime.now()


def now_iso() -> str:
    return _datetime.now().isoformat(timespec="seconds")

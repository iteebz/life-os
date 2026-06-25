from datetime import date, timedelta

from lifeos.core.lib.format import format_due


def test_format_due_today():
    today = date.today()
    result = format_due(today.isoformat(), colorize=False)
    assert result == today.strftime("%d/%m") + "·"


def test_format_due_future():
    future = date.today() + timedelta(days=5)
    result = format_due(future.isoformat(), colorize=False)
    assert result == future.strftime("%d/%m") + "·"


def test_format_due_tomorrow():
    tomorrow = date.today() + timedelta(days=1)
    result = format_due(tomorrow.isoformat(), colorize=False)
    assert result == tomorrow.strftime("%d/%m") + "·"


def test_format_due_past():
    past = date.today() - timedelta(days=3)
    result = format_due(past.isoformat(), colorize=False)
    assert result == past.strftime("%d/%m") + "·"


def test_format_due_empty():
    result = format_due("")
    assert result == ""


def test_format_due_none():
    result = format_due(None)
    assert result == ""

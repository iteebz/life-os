from datetime import date, datetime, time, timedelta

import life.lib.clock as clock
from life.contacts import add_contact
from life.nudge import (
    MAX_PER_DAY,
    Nudge,
    _count_today,
    _is_quiet,
    _record,
    _rule_contacts,
    _rule_dates,
    _rule_overdue,
    _rule_scheduled,
    _sent_today,
    evaluate_rules,
    run_cycle,
)
from life.task import add_task


def _at(hour: int, minute: int = 0, d: date | None = None) -> datetime:
    day = d or date(2025, 10, 30)
    return datetime.combine(day, time(hour, minute))


# ── quiet hours ──────────────────────────────────────────────────────────────


def test_quiet_before_10am():
    assert _is_quiet(_at(9, 59))
    assert _is_quiet(_at(0))
    assert _is_quiet(_at(5))


def test_not_quiet_during_day():
    assert not _is_quiet(_at(10, 0))
    assert not _is_quiet(_at(14))
    assert not _is_quiet(_at(22, 59))


def test_quiet_after_11pm():
    assert _is_quiet(_at(23, 0))
    assert _is_quiet(_at(23, 59))


# ── scheduled rule ───────────────────────────────────────────────────────────


def test_scheduled_within_window(tmp_life_dir, monkeypatch):
    fixed = date(2025, 10, 30)
    monkeypatch.setattr(clock, "today", lambda: fixed)
    monkeypatch.setattr(clock, "now", lambda: _at(14, 0, fixed))

    add_task("call bank", scheduled_date=fixed.isoformat(), tags=["finance"])
    from life.task import get_tasks, update_task

    t = get_tasks()[0]
    update_task(t.id, scheduled_time="14:10")

    nudges = _rule_scheduled(_at(14, 0, fixed))
    assert len(nudges) == 1
    assert "call bank" in nudges[0].message
    assert nudges[0].rule == "scheduled"


def test_scheduled_outside_window(tmp_life_dir, monkeypatch):
    fixed = date(2025, 10, 30)
    monkeypatch.setattr(clock, "today", lambda: fixed)

    add_task("later task", scheduled_date=fixed.isoformat(), tags=["admin"])
    from life.task import get_tasks, update_task

    t = get_tasks()[0]
    update_task(t.id, scheduled_time="16:00")

    nudges = _rule_scheduled(_at(14, 0, fixed))
    assert len(nudges) == 0


def test_scheduled_dedup(tmp_life_dir, monkeypatch):
    fixed = date(2025, 10, 30)
    monkeypatch.setattr(clock, "today", lambda: fixed)
    monkeypatch.setattr(clock, "now", lambda: _at(14, 0, fixed))

    add_task("duped task", scheduled_date=fixed.isoformat(), tags=["admin"])
    from life.task import get_tasks, update_task

    t = get_tasks()[0]
    update_task(t.id, scheduled_time="14:05")

    nudges = _rule_scheduled(_at(14, 0, fixed))
    assert len(nudges) == 1

    # Record it as sent
    _record(nudges[0])

    # Should not fire again
    nudges2 = _rule_scheduled(_at(14, 0, fixed))
    assert len(nudges2) == 0


# ── overdue rule ─────────────────────────────────────────────────────────────


def test_overdue_discomfort_only(tmp_life_dir, monkeypatch):
    fixed = date(2025, 10, 30)
    monkeypatch.setattr(clock, "today", lambda: fixed)
    monkeypatch.setattr(clock, "now", lambda: _at(14, 0, fixed))

    yesterday = (fixed - timedelta(days=1)).isoformat()
    add_task("pay bill", scheduled_date=yesterday, tags=["finance"])
    add_task("clean kitchen", scheduled_date=yesterday, tags=["home"])

    nudges = _rule_overdue(_at(14, 0, fixed))
    assert len(nudges) == 1
    assert "pay bill" in nudges[0].message


# ── contacts rule ────────────────────────────────────────────────────────────


def test_contact_stale(tmp_life_dir, monkeypatch):
    fixed = date(2025, 10, 30)
    monkeypatch.setattr(clock, "today", lambda: fixed)

    add_contact("test friend", cadence_days=30)
    # Never contacted — should trigger (stale > 1.5x cadence)
    nudges = _rule_contacts(_at(14, 0, fixed))
    assert len(nudges) == 1
    assert "test friend" in nudges[0].message


# ── dates rule ───────────────────────────────────────────────────────────────


def test_date_upcoming(tmp_life_dir, monkeypatch):
    fixed = date(2025, 10, 30)
    monkeypatch.setattr(clock, "today", lambda: fixed)

    from life.lib.dates import add_date

    add_date("test birthday", "31-10", type_="birthday")

    nudges = _rule_dates(_at(14, 0, fixed))
    assert len(nudges) == 1
    assert "test birthday" in nudges[0].message
    assert "1 day" in nudges[0].message


def test_date_today(tmp_life_dir, monkeypatch):
    fixed = date(2025, 10, 30)
    monkeypatch.setattr(clock, "today", lambda: fixed)

    from life.lib.dates import add_date

    add_date("test event", "30-10", type_="other")

    nudges = _rule_dates(_at(14, 0, fixed))
    assert len(nudges) == 1
    assert "today" in nudges[0].message


# ── evaluate + budget ────────────────────────────────────────────────────────


def test_evaluate_sorts_by_priority(tmp_life_dir, monkeypatch):
    fixed = date(2025, 10, 30)
    monkeypatch.setattr(clock, "today", lambda: fixed)
    monkeypatch.setattr(clock, "now", lambda: _at(14, 0, fixed))

    yesterday = (fixed - timedelta(days=1)).isoformat()
    add_task("overdue finance", scheduled_date=yesterday, tags=["finance"])
    add_task("scheduled now", scheduled_date=fixed.isoformat(), tags=["admin"])
    from life.task import get_tasks, update_task

    scheduled = next(t for t in get_tasks() if t.content == "scheduled now")
    update_task(scheduled.id, scheduled_time="14:05")

    nudges = evaluate_rules(_at(14, 0, fixed))
    assert len(nudges) >= 2
    # Scheduled with deadline would be p1, overdue is p2
    assert nudges[0].priority <= nudges[1].priority


def test_daily_budget_cap(tmp_life_dir, monkeypatch):
    fixed = date(2025, 10, 30)
    monkeypatch.setattr(clock, "today", lambda: fixed)
    monkeypatch.setattr(clock, "now", lambda: _at(14, 0, fixed))

    # Fill up the budget
    for i in range(MAX_PER_DAY):
        _record(Nudge(rule="test", entity_id=f"e{i}", message=f"test {i}", priority=2))

    assert _count_today() == MAX_PER_DAY


def test_run_cycle_respects_quiet(tmp_life_dir, monkeypatch):
    fixed = date(2025, 10, 30)
    monkeypatch.setattr(clock, "today", lambda: fixed)
    monkeypatch.setattr(clock, "now", lambda: _at(8, 0, fixed))  # before 10am

    yesterday = (fixed - timedelta(days=1)).isoformat()
    add_task("should not nudge", scheduled_date=yesterday, tags=["finance"])

    sent = run_cycle()
    assert sent == 0


def test_sent_today_tracking(tmp_life_dir, monkeypatch):
    fixed = date(2025, 10, 30)
    monkeypatch.setattr(clock, "today", lambda: fixed)
    monkeypatch.setattr(clock, "now", lambda: _at(14, 0, fixed))

    assert not _sent_today("test", "abc")
    _record(Nudge(rule="test", entity_id="abc", message="hi", priority=2))
    assert _sent_today("test", "abc")

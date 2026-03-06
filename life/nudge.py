from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from fncli import cli

from life.config import Config
from life.lib import clock
from life.lib.store import get_db

logger = logging.getLogger(__name__)

QUIET_START = 0  # midnight — no nudges before QUIET_END
QUIET_END = 10  # 10am
QUIET_NIGHT = 23  # 11pm
MAX_PER_DAY = 3
DISCOMFORT_TAGS = {"finance", "legal", "janice"}


@dataclass
class Nudge:
    rule: str  # scheduled | overdue | contact | date
    entity_id: str
    message: str
    priority: int  # 1=high, 2=normal, 3=low


def _is_quiet(now: datetime) -> bool:
    return now.hour < QUIET_END or now.hour >= QUIET_NIGHT


def _sent_today(rule: str, entity_id: str) -> bool:
    today_str = clock.today().isoformat()
    with get_db() as conn:
        row = conn.execute(
            "SELECT 1 FROM nudge_log WHERE rule = ? AND entity_id = ? AND DATE(sent_at) = ?",
            (rule, entity_id, today_str),
        ).fetchone()
    return row is not None


def _sent_this_week(rule: str, entity_id: str) -> bool:
    today = clock.today()
    week_start = (today - __import__("datetime").timedelta(days=today.weekday())).isoformat()
    with get_db() as conn:
        row = conn.execute(
            "SELECT 1 FROM nudge_log WHERE rule = ? AND entity_id = ? AND DATE(sent_at) >= ?",
            (rule, entity_id, week_start),
        ).fetchone()
    return row is not None


def _count_today() -> int:
    today_str = clock.today().isoformat()
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM nudge_log WHERE DATE(sent_at) = ?",
            (today_str,),
        ).fetchone()
    return row[0] if row else 0


def _record(nudge: Nudge) -> None:
    now_str = clock.now().strftime("%Y-%m-%dT%H:%M:%S")
    with get_db() as conn:
        conn.execute(
            "INSERT INTO nudge_log (rule, entity_id, message, sent_at) VALUES (?, ?, ?, ?)",
            (nudge.rule, nudge.entity_id, nudge.message, now_str),
        )


# ── rules ────────────────────────────────────────────────────────────────────


def _rule_scheduled(now: datetime) -> list[Nudge]:
    from life.task import get_tasks

    today = clock.today()
    nudges: list[Nudge] = []
    for t in get_tasks():
        if t.scheduled_date != today or not t.scheduled_time:
            continue
        try:
            hour, minute = (int(x) for x in t.scheduled_time.split(":"))
        except (ValueError, AttributeError):
            continue
        diff = (hour * 60 + minute) - (now.hour * 60 + now.minute)
        if 0 <= diff <= 15 and not _sent_today("scheduled", t.id):
            notes_hint = " — see task notes" if t.notes else ""
            tags = " ".join(f"#{tag}" for tag in (t.tags or []))
            tag_str = f" {tags}" if tags else ""
            nudges.append(
                Nudge(
                    rule="scheduled",
                    entity_id=t.id,
                    message=f"📋 {t.content} (scheduled {t.scheduled_time}){tag_str}{notes_hint}",
                    priority=1 if t.is_deadline else 2,
                )
            )
    return nudges


def _rule_overdue(now: datetime) -> list[Nudge]:
    from life.task import get_tasks

    today = clock.today()
    nudges: list[Nudge] = []
    for t in get_tasks():
        if not t.scheduled_date or t.scheduled_date >= today:
            continue
        task_tags = set(t.tags or [])
        if not task_tags.intersection(DISCOMFORT_TAGS):
            continue
        if _sent_today("overdue", t.id):
            continue
        days = (today - t.scheduled_date).days
        tags = " ".join(f"#{tag}" for tag in (t.tags or []))
        nudges.append(
            Nudge(
                rule="overdue",
                entity_id=t.id,
                message=f"⚠️ {t.content} — overdue {days}d {tags}",
                priority=2,
            )
        )
    return nudges


def _rule_contacts(_now: datetime) -> list[Nudge]:
    from life.contacts import get_contacts

    today = clock.today()
    nudges: list[Nudge] = []
    for c in get_contacts():
        threshold = int(c.cadence_days * 1.5)
        if c.last_contact_at is None:
            days_since = threshold + 1
        else:
            days_since = (today - c.last_contact_at.date()).days
        if days_since < threshold:
            continue
        if _sent_this_week("contact", str(c.id)):
            continue
        nudges.append(
            Nudge(
                rule="contact",
                entity_id=str(c.id),
                message=f"👋 {c.name} — haven't talked in {days_since}d",
                priority=3,
            )
        )
    return nudges


def _rule_dates(_now: datetime) -> list[Nudge]:
    from life.lib.dates import upcoming_dates

    nudges: list[Nudge] = []
    for d in upcoming_dates(within_days=2):
        entity_id = str(d["id"])
        if _sent_today("date", entity_id):
            continue
        days = d["days_until"]
        if days == 0:
            nudges.append(
                Nudge(
                    rule="date",
                    entity_id=entity_id,
                    message=f"🎯 {d['name']} is today",
                    priority=1,
                )
            )
        else:
            nudges.append(
                Nudge(
                    rule="date",
                    entity_id=entity_id,
                    message=f"🗓 {d['name']} in {days} day{'s' if days != 1 else ''}",
                    priority=2,
                )
            )
    return nudges


# ── core ─────────────────────────────────────────────────────────────────────

ALL_RULES = [_rule_scheduled, _rule_overdue, _rule_contacts, _rule_dates]


def evaluate_rules(now: datetime) -> list[Nudge]:
    nudges: list[Nudge] = []
    for rule_fn in ALL_RULES:
        nudges.extend(rule_fn(now))
    nudges.sort(key=lambda n: n.priority)
    return nudges


def _get_chat_id() -> int | None:
    from life.lib.resolve import resolve_people_field

    result = resolve_people_field("tyson", "telegram")
    return int(result) if result else None


def send_nudges(nudges: list[Nudge]) -> int:
    from life.comms.messages.telegram import send

    chat_id = _get_chat_id()
    if not chat_id:
        logger.warning("no telegram chat_id for tyson — skipping nudges")
        return 0

    sent = 0
    for nudge in nudges:
        ok, err = send(chat_id, nudge.message)
        if ok:
            _record(nudge)
            sent += 1
        else:
            logger.warning("nudge send failed: %s", err)
    return sent


def is_enabled() -> bool:
    val = Config().get("nudge_enabled", True)
    return bool(val)


def run_cycle() -> int:
    if not is_enabled():
        return 0
    now = clock.now()
    if _is_quiet(now):
        return 0
    budget = MAX_PER_DAY - _count_today()
    if budget <= 0:
        return 0
    candidates = evaluate_rules(now)
    to_send = candidates[:budget]
    if not to_send:
        return 0
    return send_nudges(to_send)


# ── cli ──────────────────────────────────────────────────────────────────────


@cli("life nudge", name="test")
def nudge_test() -> None:
    """Dry run — show what would be nudged right now"""
    now = clock.now()
    quiet = _is_quiet(now)
    budget = MAX_PER_DAY - _count_today()

    print(f"time: {now.strftime('%H:%M')}  quiet: {quiet}  budget: {budget}/{MAX_PER_DAY}")
    if quiet:
        print(f"quiet hours (before {QUIET_END}:00 or after {QUIET_NIGHT}:00)")

    candidates = evaluate_rules(now)
    if not candidates:
        print("no nudge candidates")
        return
    print(f"\ncandidates ({len(candidates)}):")
    for n in candidates:
        would = "SEND" if not quiet and budget > 0 else "SKIP"
        print(f"  [{would}] p{n.priority} {n.rule}: {n.message}")
        budget -= 1


@cli("life nudge", name="history")
def nudge_history(limit: int = 20) -> None:
    """Show recent nudge log"""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT rule, entity_id, message, sent_at FROM nudge_log ORDER BY sent_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    if not rows:
        print("no nudges sent yet")
        return
    for row in rows:
        rule, _, message, sent_at = row
        ts = datetime.fromisoformat(sent_at).strftime("%d/%m %H:%M")
        print(f"  {ts}  [{rule}] {message}")


@cli("life nudge")
def on() -> None:
    """Enable nudges"""
    Config().set("nudge_enabled", True)
    print("nudges enabled")


@cli("life nudge")
def off() -> None:
    """Disable nudges"""
    Config().set("nudge_enabled", False)
    print("nudges disabled")

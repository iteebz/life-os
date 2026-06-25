import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from fncli import cli

from lifeos.core.lib import clock
from lifeos.core.lib.dates import parse_created_date
from lifeos.core.lib.store import get_db
from lifeos.core.models import Weekly

__all__ = ["Momentum", "compute", "weekly_momentum"]

TAG_WEIGHTS = {
    "janice": 3.0,
    "finance": 3.0,
    "legal": 3.0,
    "health": 2.0,
    "comms": 2.0,
    "family": 2.0,
    "admin": 1.5,
    "errand": 1.5,
    "home": 1.5,
    "wedding": 1.5,
    "chore": 1.0,
    "hygiene": 1.0,
    "hobby": 0.7,
    "social": 0.7,
    "sell": 0.7,
    "vice": 0.0,
}
DEFAULT_WEIGHT = 0.3
HABIT_SCALE = 0.5
HALF_LIFE_HOURS = 24
WINDOW_HOURS = 48
STALE_DAYS = 7
STALE_PENALTY_K = 3
STALE_PENALTY_CAP = 15
DISCOMFORT_TAGS = {"janice", "finance", "legal"}
SCALE = 10


@dataclass(frozen=True)
class Momentum:
    score: int
    delta: int
    raw: float
    stale: int
    penalty: float


def _parse(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts)
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def _tag_weight(tags: set[str]) -> float:
    return max((TAG_WEIGHTS.get(t, DEFAULT_WEIGHT) for t in tags), default=DEFAULT_WEIGHT)


def _load_events(conn) -> list[tuple[datetime, float, set[str]]]:
    """All scoring events in last WINDOW_HOURS: tasks done + habit checks."""
    task_tags: dict[str, set[str]] = defaultdict(set)
    habit_tags: dict[str, set[str]] = defaultdict(set)
    for tid, tag in conn.execute("SELECT task_id, tag FROM tags WHERE task_id IS NOT NULL"):
        task_tags[tid].add(tag)
    for hid, tag in conn.execute("SELECT habit_id, tag FROM tags WHERE habit_id IS NOT NULL"):
        habit_tags[hid].add(tag)

    events: list[tuple[datetime, float, set[str]]] = []
    cutoff = (datetime.now(UTC) - timedelta(hours=WINDOW_HOURS + 1)).isoformat()

    for tid, completed in conn.execute(
        "SELECT id, completed_at FROM tasks WHERE completed_at IS NOT NULL AND deleted_at IS NULL AND completed_at >= ?",
        (cutoff,),
    ):
        tags = task_tags.get(tid, set())
        events.append((_parse(completed), _tag_weight(tags), tags))

    for hid, completed in conn.execute(
        "SELECT habit_id, completed_at FROM habit_checks WHERE completed_at >= ?",
        (cutoff,),
    ):
        tags = habit_tags.get(hid, set())
        events.append((_parse(completed), HABIT_SCALE * _tag_weight(tags), tags))

    return events


def _stale_count(conn, asof: datetime) -> int:
    task_tags: dict[str, set[str]] = defaultdict(set)
    for tid, tag in conn.execute("SELECT task_id, tag FROM tags WHERE task_id IS NOT NULL"):
        task_tags[tid].add(tag)
    cutoff = (asof - timedelta(days=STALE_DAYS)).isoformat()
    count = 0
    for (tid,) in conn.execute(
        "SELECT id FROM tasks WHERE completed_at IS NULL AND deleted_at IS NULL AND created <= ?",
        (cutoff,),
    ):
        if task_tags.get(tid, set()) & DISCOMFORT_TAGS:
            count += 1
    return count


def _score_at(asof: datetime, events, stale: int) -> tuple[int, float, float]:
    raw = 0.0
    for ts, weight, _ in events:
        age_h = (asof - ts).total_seconds() / 3600
        if 0 <= age_h <= WINDOW_HOURS:
            raw += weight * math.exp(-age_h / HALF_LIFE_HOURS)
    penalty = min(STALE_PENALTY_CAP, STALE_PENALTY_K * math.sqrt(stale))
    score = max(0, min(99, round(raw * SCALE - penalty)))
    return score, raw, penalty


def compute(now: datetime | None = None) -> Momentum:
    """Current momentum + delta vs 24h ago. Pure read."""
    now = now or datetime.now(UTC)
    with get_db() as conn:
        events = _load_events(conn)
        stale = _stale_count(conn, now)
        score, raw, penalty = _score_at(now, events, stale)
        # delta: compare to score 24h ago (same stale count — approximation)
        prev, _, _ = _score_at(now - timedelta(hours=24), events, stale)
    return Momentum(score=score, delta=score - prev, raw=raw, stale=stale, penalty=penalty)


@cli("life")
def momentum(explain: bool = False) -> None:
    """Current momentum score (0-99) with 24h trend."""
    m = compute()
    arrow = "↑" if m.delta >= 3 else ("↓" if m.delta <= -3 else "·")
    print(f"M{m.score} {arrow}{abs(m.delta) if abs(m.delta) >= 3 else ''}".strip())
    if explain:
        print(f"  raw={m.raw:.2f} x {SCALE} = {m.raw * SCALE:.1f}")
        print(f"  stale discomfort: {m.stale} (penalty -{m.penalty:.1f})")
        with get_db() as conn:
            events = _load_events(conn)
        now = datetime.now(UTC)
        contribs = []
        for ts, weight, tags in events:
            age_h = (now - ts).total_seconds() / 3600
            if 0 <= age_h <= WINDOW_HOURS:
                contribs.append((weight * math.exp(-age_h / HALF_LIFE_HOURS), age_h, tags))
        print("  top contributors:")
        for c, age, tags in sorted(contribs, reverse=True)[:5]:
            tag_str = ",".join(sorted(tags)) or "(untagged)"
            print(f"    +{c:.2f}  {age:4.1f}h  {tag_str}")


def _calculate_total_possible(active_items_data, week_start_date, week_end_date):
    total_possible = 0
    for row in active_items_data:
        _item_id = row[0]
        created_val = row[1]
        cadence = row[2] if len(row) > 2 else "daily"

        created_date = parse_created_date(created_val)

        if created_date > week_end_date:
            continue

        effective_start_date = max(created_date, week_start_date)

        if effective_start_date > week_end_date:
            continue

        if cadence == "weekly":
            total_possible += 1
        else:
            days_active = (week_end_date - effective_start_date).days + 1
            total_possible += days_active

    return total_possible


def weekly_momentum():
    """Get weekly totals: this week, last week, prior week"""
    today = clock.today()

    this_week_start = today - timedelta(days=6)
    this_week_end = today

    last_week_start = today - timedelta(days=13)
    last_week_end = today - timedelta(days=7)

    prior_week_start = today - timedelta(days=20)
    prior_week_end = today - timedelta(days=14)

    weeks = {}

    with get_db() as conn:
        for week_name, start_date, end_date in [
            ("this_week", this_week_start, this_week_end),
            ("last_week", last_week_start, last_week_end),
            ("prior_week", prior_week_start, prior_week_end),
        ]:
            start_str = start_date.isoformat()
            end_str = end_date.isoformat()
            cursor = conn.execute(
                """
                SELECT COUNT(*)
                FROM tasks
                WHERE completed_at >= ?
                AND completed_at <= ?
                AND completed_at IS NOT NULL""",
                (start_str, end_str),
            )
            tasks = cursor.fetchone()[0]

            cursor = conn.execute(
                """
                SELECT COUNT(*)
                FROM habit_checks c
                WHERE c.check_date >= ?
                AND c.check_date <= ?""",
                (start_str, end_str),
            )
            habits = cursor.fetchone()[0]

            cursor = conn.execute(
                """
                SELECT COUNT(*)
                FROM tasks
                WHERE (
                    created <= ?
                    OR (completed_at >= ? AND completed_at <= ?)
                )""",
                (end_str, start_str, end_str),
            )
            tasks_total = cursor.fetchone()[0]

            cursor = conn.execute(
                """
                SELECT DISTINCT
                    h.id,
                    h.created,
                    h.cadence
                FROM habits h"""
            )
            active_habits_data = cursor.fetchall()

            habits_total_possible = _calculate_total_possible(
                active_habits_data,
                date.fromisoformat(start_str),
                date.fromisoformat(end_str),
            )

            weeks[week_name] = Weekly(
                tasks_completed=tasks,
                tasks_total=tasks_total,
                habits_completed=habits,
                habits_total=habits_total_possible,
            )

    return weeks

#!/usr/bin/env python3
"""Exploratory: compute momentum M over last 30 days, hourly. Print ASCII chart.

Not wired anywhere. Run, look at the curve, tweak weights, repeat.
"""

import math
import sqlite3
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

DB = Path.home() / ".life" / "life.db"

# tweak these freely
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
HALF_LIFE_HOURS = 24  # decay constant: e^(-h / HL)
WINDOW_HOURS = 48  # cutoff
STALE_DAYS = 7  # discomfort age threshold
STALE_PENALTY = 5  # points per stale discomfort task (post-clamp scale)
DISCOMFORT_TAGS = {"janice", "finance", "legal"}
SCALE = 10  # raw → display multiplier


def load_done_tasks(conn):
    """Returns list of (completed_at: datetime, weight: float)."""
    rows = conn.execute("""
        SELECT t.id, t.completed_at
        FROM tasks t
        WHERE t.completed_at IS NOT NULL
          AND t.deleted_at IS NULL
          AND t.completed_at >= datetime('now', '-35 days')
    """).fetchall()
    tag_map = defaultdict(set)
    for tid, tag in conn.execute("SELECT task_id, tag FROM tags WHERE task_id IS NOT NULL"):
        tag_map[tid].add(tag)
    out = []
    for tid, completed in rows:
        ts = datetime.fromisoformat(completed)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        tags = tag_map.get(tid, set())
        weight = max((TAG_WEIGHTS.get(t, DEFAULT_WEIGHT) for t in tags), default=DEFAULT_WEIGHT)
        out.append((ts, weight, tags))
    return out


def load_open_discomfort(conn, asof):
    """Open discomfort tasks aged > STALE_DAYS at `asof`."""
    rows = conn.execute("""
        SELECT t.id, t.created
        FROM tasks t
        WHERE t.completed_at IS NULL
          AND t.deleted_at IS NULL
    """).fetchall()
    tag_map = defaultdict(set)
    for tid, tag in conn.execute("SELECT task_id, tag FROM tags WHERE task_id IS NOT NULL"):
        tag_map[tid].add(tag)
    count = 0
    for tid, created in rows:
        if not (tag_map.get(tid, set()) & DISCOMFORT_TAGS):
            continue
        ts = datetime.fromisoformat(created)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        if (asof - ts).days >= STALE_DAYS:
            count += 1
    return count


def momentum(asof, done, conn):
    raw = 0.0
    for ts, weight, _ in done:
        age_h = (asof - ts).total_seconds() / 3600
        if age_h < 0 or age_h > WINDOW_HOURS:
            continue
        raw += weight * math.exp(-age_h / HALF_LIFE_HOURS)
    stale = load_open_discomfort(conn, asof)
    score = round(raw * SCALE) - STALE_PENALTY * stale
    return max(0, min(99, score)), raw, stale


def ascii_chart(series, height=12, width=None):
    if not series:
        return "(empty)"
    width = width or len(series)
    vals = [v for _, v in series]
    hi = max(vals) or 1
    lines = []
    for row in range(height, 0, -1):
        threshold = hi * row / height
        line = "".join("█" if v >= threshold else " " for v in vals)
        lines.append(f"{int(threshold):3d} │{line}")
    lines.append("    └" + "─" * len(vals))
    return "\n".join(lines)


def main():
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    done = load_done_tasks(conn)
    print(f"loaded {len(done)} done tasks (last 35d)")

    now = datetime.now(UTC)
    series = []
    for hours_ago in range(30 * 24, -1, -6):  # every 6h, 30d back
        asof = now - timedelta(hours=hours_ago)
        score, raw, stale = momentum(asof, done, conn)
        series.append((asof, score))

    print()
    print(ascii_chart(series))
    print()

    # current breakdown
    score, raw, stale = momentum(now, done, conn)
    print(f"NOW: M={score}  raw={raw:.2f}  stale_discomfort={stale}")
    print()
    print("top contributors (now):")
    contribs = []
    for ts, weight, tags in done:
        age_h = (now - ts).total_seconds() / 3600
        if 0 <= age_h <= WINDOW_HOURS:
            contribs.append((weight * math.exp(-age_h / HALF_LIFE_HOURS), age_h, tags))
    for c, age, tags in sorted(contribs, reverse=True)[:8]:
        print(f"  +{c:.2f}  age={age:5.1f}h  tags={sorted(tags)}")


if __name__ == "__main__":
    main()

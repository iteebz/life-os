from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fncli import cli

from .db import get_db
from .lib.errors import exit_error


@dataclass(frozen=True)
class MoodEntry:
    id: int
    score: int
    label: str | None
    logged_at: datetime


def add_mood(score: int, label: str | None = None) -> int:
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO mood_log (score, label) VALUES (?, ?)",
            (score, label),
        )
        return cursor.lastrowid or 0


def get_recent_moods(hours: int = 24) -> list[MoodEntry]:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, score, label, logged_at FROM mood_log WHERE logged_at > ? ORDER BY logged_at DESC",
            (cutoff.isoformat(),),
        ).fetchall()
    return [
        MoodEntry(id=row[0], score=row[1], label=row[2], logged_at=datetime.fromisoformat(row[3]))
        for row in rows
    ]


def get_latest_mood() -> MoodEntry | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, score, label, logged_at FROM mood_log ORDER BY logged_at DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    return MoodEntry(
        id=row[0], score=row[1], label=row[2], logged_at=datetime.fromisoformat(row[3])
    )


def delete_latest_mood(within_seconds: int = 3600) -> MoodEntry | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, score, label, logged_at FROM mood_log ORDER BY logged_at DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        logged_at = datetime.fromisoformat(row[3])
        if logged_at.tzinfo is None:
            logged_at = logged_at.replace(tzinfo=UTC)
        entry = MoodEntry(id=row[0], score=row[1], label=row[2], logged_at=logged_at)
        age = (datetime.now(UTC) - entry.logged_at).total_seconds()
        if age > within_seconds:
            raise ValueError(f"latest entry is {int(age // 60)}m old — too old to remove")
        conn.execute("DELETE FROM mood_log WHERE id = ?", (row[0],))
    return entry


@cli("life mood", name="log")
def log(score: int, label: str | None = None):
    """Log energy/mood (1-5) with optional label"""
    if score < 1 or score > 5:
        exit_error("Score must be 1-5")
    add_mood(score, label)
    bar = "█" * score + "░" * (5 - score)
    label_str = f"  {label}" if label else ""
    print(f"→ {bar}  {score}/5{label_str}")


@cli("life mood", name="show")
def show():
    """View rolling 24h mood window"""
    from .lib.format import format_elapsed

    entries = get_recent_moods(hours=24)
    if not entries:
        print("no mood logged in the last 24h")
        return
    now_dt = datetime.now()
    for e in entries:
        rel = format_elapsed(e.logged_at, now_dt)
        bar = "█" * e.score + "░" * (5 - e.score)
        label_str = f"  {e.label}" if e.label else ""
        print(f"  {rel:<10}  {bar}  {e.score}/5{label_str}")


@cli("life mood", name="rm")
def rm():
    """Remove latest mood entry"""
    entry = delete_latest_mood()
    if not entry:
        exit_error("no mood entries to remove")
        return
    bar = "█" * entry.score + "░" * (5 - entry.score)
    label_str = f"  {entry.label}" if entry.label else ""
    print(f"✗ {bar}  {entry.score}/5{label_str}")

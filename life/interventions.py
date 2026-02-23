from dataclasses import dataclass
from datetime import datetime

from fncli import cli

from .db import get_db


@dataclass(frozen=True)
class Intervention:
    id: int
    timestamp: datetime
    description: str
    result: str
    note: str | None


def add_intervention(description: str, result: str, note: str | None = None) -> int:
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO interventions (description, result, note) VALUES (?, ?, ?)",
            (description, result, note),
        )
        return cursor.lastrowid or 0


def get_interventions(limit: int = 20) -> list[Intervention]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, timestamp, description, result, note FROM interventions ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            Intervention(
                id=row[0],
                timestamp=datetime.fromisoformat(row[1]),
                description=row[2],
                result=row[3],
                note=row[4],
            )
            for row in rows
        ]


def get_stats() -> dict[str, int]:
    with get_db() as conn:
        rows = conn.execute("SELECT result, COUNT(*) FROM interventions GROUP BY result").fetchall()
        return {row[0]: row[1] for row in rows}


@cli("life track", name="log")
def log():
    """Show recent intervention log"""
    interventions = get_interventions(20)
    if not interventions:
        print("no interventions logged")
        return
    for intervention in interventions:
        ts = intervention.timestamp.strftime("%m-%d %H:%M")
        note_str = f"  ({intervention.note})" if intervention.note else ""
        print(f"{ts}  {intervention.result:<8}  {intervention.description}{note_str}")


@cli("life track", name="stats")
def stats():
    """Show intervention stats"""
    totals = get_stats()
    total = sum(totals.values())
    if not total:
        print("no interventions logged")
        return
    won = totals.get("won", 0)
    lost = totals.get("lost", 0)
    deferred = totals.get("deferred", 0)
    win_rate = int((won / total) * 100) if total else 0
    print(f"won: {won}  lost: {lost}  deferred: {deferred}  total: {total}  win_rate: {win_rate}%")


@cli("life track", name="won")
def won(description: str, note: str | None = None):
    """Log a won intervention"""
    add_intervention(description, "won", note)
    print(f"✓ {description}")


@cli("life track", name="lost")
def lost(description: str, note: str | None = None):
    """Log a lost intervention"""
    add_intervention(description, "lost", note)
    print(f"✗ {description}")


@cli("life track", name="deferred")
def deferred(description: str, note: str | None = None):
    """Log a deferred intervention"""
    add_intervention(description, "deferred", note)
    print(f"→ {description}")

from dataclasses import dataclass
from datetime import datetime

from fncli import cli

from .db import get_db
from .lib.errors import exit_error


@dataclass(frozen=True)
class Pattern:
    id: int
    body: str
    logged_at: datetime
    tag: str | None = None


def add_pattern(body: str, tag: str | None = None) -> int:
    with get_db() as conn:
        cursor = conn.execute("INSERT INTO patterns (body, tag) VALUES (?, ?)", (body, tag))
        return cursor.lastrowid or 0


def delete_pattern(pattern_id: int) -> bool:
    with get_db() as conn:
        cursor = conn.execute("DELETE FROM patterns WHERE id = ?", (pattern_id,))
        return cursor.rowcount > 0


def get_patterns(limit: int = 20, tag: str | None = None) -> list[Pattern]:
    with get_db() as conn:
        if tag:
            rows = conn.execute(
                "SELECT id, body, logged_at, tag FROM patterns WHERE tag = ? ORDER BY logged_at DESC LIMIT ?",
                (tag, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, body, logged_at, tag FROM patterns ORDER BY logged_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            Pattern(id=row[0], body=row[1], logged_at=datetime.fromisoformat(row[2]), tag=row[3])
            for row in rows
        ]


@cli("life pattern", name="log")
def log(limit: int = 20, tag: str | None = None):
    """Review logged patterns"""
    patterns = get_patterns(limit, tag=tag)
    if not patterns:
        print("no patterns logged")
        return
    now = datetime.now()
    for p in patterns:
        delta = now - p.logged_at
        s = delta.total_seconds()
        if s < 3600:
            rel = f"{int(s // 60)}m ago"
        elif s < 86400:
            rel = f"{int(s // 3600)}h ago"
        elif s < 86400 * 7:
            rel = f"{int(s // 86400)}d ago"
        else:
            rel = p.logged_at.strftime("%Y-%m-%d")
        tag_suffix = f"  [{p.tag}]" if p.tag else ""
        print(f"{rel:<10}  {p.body}{tag_suffix}")


@cli("life pattern", name="add")
def add(body: str, tag: str | None = None):
    """Log a new pattern"""
    add_pattern(body, tag=tag)
    print(f"→ {body}")


@cli("life pattern", name="rm")
def rm(ref: str):
    """Remove a pattern by ID or fuzzy match"""
    patterns = get_patterns(limit=50)
    if not patterns:
        exit_error("no patterns to remove")
        return
    if ref == "":
        target = patterns[0]
    else:
        q = ref.lower()
        matches = [p for p in patterns if q in p.body.lower()]
        if not matches:
            exit_error(f"no pattern matching '{ref}'")
            return
        target = matches[0]
    deleted = delete_pattern(target.id)
    if deleted:
        print(f"→ removed: {target.body[:80]}")
    else:
        exit_error("delete failed")

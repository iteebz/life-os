from dataclasses import dataclass
from datetime import datetime

from fncli import cli

from .db import get_db
from .lib.errors import echo, exit_error


@dataclass(frozen=True)
class Learning:
    id: int
    body: str
    tags: str | None
    logged_at: datetime


def add_learning(body: str, tags: str | None = None) -> int:
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO learnings (body, tags) VALUES (?, ?)",
            (body, tags),
        )
        return cursor.lastrowid or 0


def get_learnings() -> list[Learning]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, body, tags, logged_at FROM learnings ORDER BY logged_at DESC"
        ).fetchall()
    return [
        Learning(id=row[0], body=row[1], tags=row[2], logged_at=datetime.fromisoformat(row[3]))
        for row in rows
    ]


@cli("life add", name="a", flags={"description": ["-d", "--description"], "tags": ["-t", "--tags"]})
def add_achievement(name: str, description: str | None = None, tags: str | None = None):
    """Log an achievement"""
    from .achievements import add_achievement as _add

    _add(name, description, tags)
    echo(f"★ {name}")


@cli("life add", name="t", flags={"tag": ["-t", "--tag"], "due": ["-d", "--due"]})
def add_task(content: list[str], tag: list[str] | None = None, due: str | None = None):
    """Add a task"""
    from .lib.dates import parse_due_date
    from .tasks import add_task as _add
    from .tasks import format_status

    content_str = " ".join(content) if content else ""
    if not content_str:
        exit_error("Usage: life add t <task>")
    tags = list(tag) if tag else []
    due_date = parse_due_date(due) if due else None
    task_id = _add(content_str, tags=tags, scheduled_date=due_date)
    echo(format_status("□", content_str, task_id))


@cli("life add", name="h", flags={"tag": ["-t", "--tag"]})
def add_habit(content: list[str], tag: list[str] | None = None):
    """Add a habit"""
    from .habits import add_habit as _add
    from .habits import format_status

    content_str = " ".join(content) if content else ""
    if not content_str:
        exit_error("Usage: life add h <habit>")
    tags = list(tag) if tag else []
    habit_id = _add(content_str, tags=tags)
    echo(format_status("□", content_str, habit_id))


@cli("life add", name="o", flags={"tag": ["-t", "--tag"]})
def add_observation(body: str, tag: str | None = None):
    """Log an observation"""
    from .steward import add_observation as _add

    _add(body, tag=tag)
    suffix = f" #{tag}" if tag else ""
    echo(f"→ {body}{suffix}")


@cli("life add", name="p", flags={"tag": ["-t", "--tag"]})
def add_pattern(body: str, tag: str | None = None):
    """Log a pattern"""
    from .patterns import add_pattern as _add

    _add(body, tag=tag)
    suffix = f" #{tag}" if tag else ""
    echo(f"~ {body}{suffix}")


@cli("life add", name="l", flags={"tags": ["-t", "--tags"]})
def add_learning_cmd(body: str, tags: str | None = None):
    """Log a steward learning"""
    add_learning(body, tags)
    suffix = f" [{tags}]" if tags else ""
    echo(f"◆ {body}{suffix}")

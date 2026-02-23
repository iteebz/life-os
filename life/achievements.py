from dataclasses import dataclass
from datetime import datetime

from fncli import cli

from .db import get_db
from .lib.ansi import ANSI, bold, dim, gray, white
from .lib.errors import echo


@dataclass(frozen=True)
class Achievement:
    id: int
    name: str
    description: str | None
    tags: str | None
    achieved_at: datetime


def add_achievement(name: str, description: str | None = None, tags: str | None = None) -> int:
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO achievements (name, description, tags) VALUES (?, ?, ?)",
            (name, description, tags),
        )
        return cursor.lastrowid or 0


def get_achievements() -> list[Achievement]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, name, description, tags, achieved_at FROM achievements ORDER BY achieved_at DESC"
        ).fetchall()
    return [
        Achievement(
            id=row[0],
            name=row[1],
            description=row[2],
            tags=row[3],
            achieved_at=datetime.fromisoformat(row[4]),
        )
        for row in rows
    ]


@cli(
    "life achievement",
    name="log",
    flags={"description": ["-d", "--description"], "tags": ["-t", "--tags"]},
)
def log(name: str, description: str | None = None, tags: str | None = None):
    """Log an achievement"""
    add_achievement(name, description, tags)
    echo(f"★ {name}")


def _achievement_tag_colors(entries: list["Achievement"]) -> dict[str, str]:
    all_tags: list[str] = []
    for e in entries:
        if e.tags:
            all_tags.extend(t.strip() for t in e.tags.split(","))
    unique = sorted(set(all_tags))
    return {tag: ANSI.POOL[i % len(ANSI.POOL)] for i, tag in enumerate(unique)}


def update_achievement(
    id: int,
    name: str | None = None,
    description: str | None = None,
    tags: str | None = None,
) -> None:
    fields = []
    values = []
    if name is not None:
        fields.append("name = ?")
        values.append(name)
    if description is not None:
        fields.append("description = ?")
        values.append(description)
    if tags is not None:
        fields.append("tags = ?")
        values.append(tags)
    if not fields:
        return
    values.append(id)
    with get_db() as conn:
        conn.execute(f"UPDATE achievements SET {', '.join(fields)} WHERE id = ?", values)  # noqa: S608


@cli(
    "life achievement",
    name="update",
    flags={
        "name": ["-n", "--name"],
        "description": ["-d", "--description"],
        "tags": ["-t", "--tags"],
    },
)
def update(
    id: int, name: str | None = None, description: str | None = None, tags: str | None = None
):
    """Update an achievement"""
    update_achievement(id, name, description, tags)
    echo(f"✓ updated {id}")


@cli("life achievement", name="ls")
def ls():
    """List all achievements"""
    entries = get_achievements()
    if not entries:
        echo("no achievements yet")
        return
    _r = ANSI.RESET
    _grey = ANSI.MUTED
    tag_colors = _achievement_tag_colors(entries)
    echo(bold(white("ACHIEVEMENTS:")))
    for e in entries:
        date_str = dim(e.achieved_at.strftime("%d/%m/%y").lower())
        dot = gray("·")
        name_str = bold(e.name)
        desc_str = f" {dim('—')} {e.description}" if e.description else ""
        if e.tags:
            tag_parts = [
                f"{tag_colors.get(t.strip(), _grey)}#{t.strip()}{_r}" for t in e.tags.split(",")
            ]
            tags_str = "  " + " ".join(tag_parts)
        else:
            tags_str = ""
        echo(f"  {date_str} {dot} {name_str}{desc_str}{tags_str}")

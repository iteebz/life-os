import uuid as _uuid
from dataclasses import dataclass
from datetime import datetime
from difflib import get_close_matches

from fncli import UsageError, cli

from .core.errors import AmbiguousError
from .db import get_db
from .lib import ansi
from .lib.ansi import POOL, dim, gray, white


@dataclass(frozen=True)
class Achievement:
    id: int
    uuid: str
    name: str
    tags: str | None
    achieved_at: datetime


def add_achievement(name: str, tags: str | None = None) -> str:
    a_uuid = _uuid.uuid4().hex[:8]
    with get_db() as conn:
        conn.execute(
            "INSERT INTO achievements (uuid, name, tags) VALUES (?, ?, ?)",
            (a_uuid, name, tags),
        )
    return a_uuid


def get_achievements() -> list[Achievement]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, uuid, name, tags, achieved_at FROM achievements ORDER BY achieved_at DESC"
        ).fetchall()
    return [
        Achievement(
            id=row[0],
            uuid=row[1] or "",
            name=row[2],
            tags=row[3],
            achieved_at=datetime.fromisoformat(row[4]),
        )
        for row in rows
    ]


def find_achievement(ref: str, pool: list[Achievement] | None = None) -> Achievement:
    entries = pool if pool is not None else get_achievements()
    ref_lower = ref.lower()
    # UUID prefix
    uuid_matches = [e for e in entries if e.uuid.startswith(ref_lower)]
    if len(uuid_matches) == 1:
        return uuid_matches[0]
    if len(uuid_matches) > 1:
        raise AmbiguousError(
            ref, count=len(uuid_matches), sample=[e.uuid for e in uuid_matches[:3]]
        )
    # exact name
    exact = next((e for e in entries if e.name.lower() == ref_lower), None)
    if exact:
        return exact
    # substring
    substr = [e for e in entries if ref_lower in e.name.lower()]
    if len(substr) == 1:
        return substr[0]
    if len(substr) > 1:
        raise AmbiguousError(ref, count=len(substr), sample=[e.name for e in substr[:3]])
    # fuzzy
    close = get_close_matches(ref_lower, [e.name.lower() for e in entries], n=1, cutoff=0.6)
    if close:
        match = next(e for e in entries if e.name.lower() == close[0])
        print(f"→ matched: {match.name}")
        return match
    raise UsageError(f"no achievement matching '{ref}'")


def _tag_colors(entries: list[Achievement]) -> dict[str, str]:
    all_tags: list[str] = []
    for e in entries:
        if e.tags:
            all_tags.extend(t.strip() for t in e.tags.split(","))
    unique = sorted(set(all_tags))
    return {tag: POOL[i % len(POOL)][0] for i, tag in enumerate(unique)}


def _print_achievements(entries: list[Achievement]) -> None:
    if not entries:
        print("no achievements yet")
        return
    tag_colors = _tag_colors(entries)
    print(white("ACHIEVEMENTS:"))
    for e in entries:
        date_str = dim(e.achieved_at.strftime("%d/%m/%y").lower())
        dot = gray("·")
        uuid_str = ansi.muted(f"[{e.uuid[:8]}]")
        if e.tags:
            tag_parts = [
                f"{tag_colors.get(t.strip(), ansi._active.muted)}#{t.strip()}{ansi._active.reset}"
                for t in e.tags.split(",")
            ]
            tags_str = "  " + " ".join(tag_parts)
        else:
            tags_str = ""
        print(f"  {date_str} {dot} {e.name}{tags_str}  {uuid_str}")


@cli("life", flags={"ref": [], "tags": ["-t"]})
def achieve(ref: list[str] | None = None, tags: str | None = None) -> None:
    """List achievements or log one: `life achieve "name"`"""
    if not ref:
        _print_achievements(get_achievements())
        return
    name = " ".join(ref)
    add_achievement(name, tags)
    print(f"★ {name}")


@cli("life achieve", flags={"ref": []})
def rm(ref: list[str]) -> None:
    """Remove an achievement by name or UUID prefix"""
    a = find_achievement(" ".join(ref))
    with get_db() as conn:
        conn.execute("DELETE FROM achievements WHERE id = ?", (a.id,))
    print(f"✗ {a.name}")


@cli(
    "life achieve",
    flags={"ref": [], "name": ["-n"], "tags": ["-t"]},
)
def update(ref: list[str], name: str | None = None, tags: str | None = None) -> None:
    """Update an achievement by name or UUID prefix"""
    a = find_achievement(" ".join(ref))
    fields, values = [], []
    if name is not None:
        fields.append("name = ?")
        values.append(name)
    if tags is not None:
        fields.append("tags = ?")
        values.append(tags)
    if not fields:
        raise UsageError("nothing to update — use -n for name, -t for tags")
    values.append(a.id)
    with get_db() as conn:
        conn.execute(f"UPDATE achievements SET {', '.join(fields)} WHERE id = ?", values)  # noqa: S608
    print(f"✓ {name or a.name}")

import uuid
from dataclasses import dataclass
from datetime import datetime

from fncli import cli

from life.lib.store import get_db

VALID_ENTITY_TYPES = {"task", "habit", "habit_check", "observation", "improvement", "mood"}


@dataclass(frozen=True)
class Note:
    id: str
    entity_type: str
    entity_id: str
    body: str
    logged_at: datetime


def add_note(entity_type: str, entity_id: str, body: str) -> str:
    if entity_type not in VALID_ENTITY_TYPES:
        msg = f"unknown entity type: {entity_type}. valid: {', '.join(sorted(VALID_ENTITY_TYPES))}"
        raise ValueError(msg)
    note_id = str(uuid.uuid4())
    with get_db() as conn:
        conn.execute(
            "INSERT INTO notes (id, entity_type, entity_id, body) VALUES (?, ?, ?, ?)",
            (note_id, entity_type, entity_id, body),
        )
    return note_id


def get_notes(entity_type: str, entity_id: str) -> list[Note]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, entity_type, entity_id, body, logged_at FROM notes "
            "WHERE entity_type = ? AND entity_id = ? AND deleted_at IS NULL "
            "ORDER BY logged_at ASC",
            (entity_type, entity_id),
        ).fetchall()
    return [
        Note(id=r[0], entity_type=r[1], entity_id=r[2], body=r[3], logged_at=datetime.fromisoformat(r[4])) for r in rows
    ]


@cli("life")
def note(entity_type: str, entity_id: str, body: str) -> None:
    """Add a note to any entity. entity_type: task|habit|habit_check|observation|improvement|mood"""
    note_id = add_note(entity_type, entity_id, body)
    print(f"noted [{entity_type}/{entity_id[:8]}] → {note_id[:8]}")

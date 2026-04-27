from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from difflib import get_close_matches

from fncli import UsageError, cli

from life.lib import ansi, clock
from life.lib.store import get_db

_COLS = "id, name, cadence_days, last_contact_at, created_at"
_ACTIVE = "deleted_at IS NULL"


@dataclass(frozen=True)
class Contact:
    id: int
    name: str
    cadence_days: int
    last_contact_at: datetime | None
    created_at: datetime


def add_contact(name: str, cadence_days: int = 30) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO contacts (name, cadence_days) VALUES (?, ?)",
            (name, cadence_days),
        )


def find_contact(name: str) -> Contact | None:
    contacts = get_contacts()
    lower = name.lower()
    exact = next((c for c in contacts if c.name.lower() == lower), None)
    if exact:
        return exact
    substr = [c for c in contacts if lower in c.name.lower()]
    if len(substr) == 1:
        return substr[0]
    names = [c.name.lower() for c in contacts]
    close = get_close_matches(lower, names, n=1, cutoff=0.6)
    if close:
        return next(c for c in contacts if c.name.lower() == close[0])
    return None


def log_contact(name: str, date: str | None = None) -> Contact | None:
    contact = find_contact(name)
    if not contact:
        return None
    ts = datetime.fromisoformat(date).isoformat() if date else datetime.now().isoformat()
    with get_db() as conn:
        conn.execute(
            "UPDATE contacts SET last_contact_at = ? WHERE id = ?",
            (ts, contact.id),
        )
    return _get_contact_by_id(contact.id)


def get_contacts() -> list[Contact]:
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT {_COLS} FROM contacts WHERE {_ACTIVE} ORDER BY name"  # noqa: S608
        ).fetchall()
    return [_row_to_contact(r) for r in rows]


def get_stale_contacts() -> list[tuple[Contact, int | None]]:
    today = clock.today()
    contacts = get_contacts()
    stale: list[tuple[Contact, int | None]] = []
    for c in contacts:
        if c.last_contact_at is None:
            stale.append((c, None))
        else:
            days_since = (today - c.last_contact_at.date()).days
            if days_since >= c.cadence_days:
                stale.append((c, days_since))
    return sorted(stale, key=lambda x: -(x[1] or 9999))


def _get_contact_by_id(contact_id: int) -> Contact | None:
    with get_db() as conn:
        row = conn.execute(
            f"SELECT {_COLS} FROM contacts WHERE id = ? AND {_ACTIVE}",  # noqa: S608
            (contact_id,),
        ).fetchone()
    return _row_to_contact(row) if row else None


def _row_to_contact(row: tuple[object, ...]) -> Contact:
    return Contact(
        id=int(row[0]),  # type: ignore[arg-type]
        name=str(row[1]),
        cadence_days=int(row[2]),  # type: ignore[arg-type]
        last_contact_at=(datetime.fromisoformat(str(row[3])) if row[3] else None),
        created_at=datetime.fromisoformat(str(row[4])),
    )


def _render_contacts() -> str:
    today = clock.today()
    contacts = get_contacts()
    if not contacts:
        return "no contacts tracked"
    lines = [f"{ansi.white('CONTACTS')}\n"]
    for c in contacts:
        if c.last_contact_at:
            days = (today - c.last_contact_at.date()).days
            days_str = f"{days}d ago"
        else:
            days_str = "never"
            days = c.cadence_days  # force overdue styling
        overdue = days >= c.cadence_days
        status = ansi.red(days_str) if overdue else ansi.dim(days_str)
        every = ansi.dim(f"every {c.cadence_days}d")
        lines.append(f"  {c.name:<12} {status:<16} {every}")
    return "\n".join(lines)


# ── cli ──────────────────────────────────────────────────────────────────────


@cli("life")
def contacts() -> None:
    """List tracked contacts with staleness"""
    print(_render_contacts())


@cli("life contacts")
def add(name: str, every: int = 30) -> None:
    """Add a contact to track: `life contacts add "name" --every 30`"""
    add_contact(name, cadence_days=every)
    print(f"→ {name} (every {every}d)")


@cli("life contacts")
def log(name: str, date: str | None = None) -> None:
    """Log contact with someone: `life contacts log "name" --date 2026-04-18`"""
    contact = log_contact(name, date=date)
    if not contact:
        raise UsageError(f"no contact matching '{name}'")
    print(f"✓ {contact.name} — logged")


@cli("life contacts")
def rm(name: str) -> None:
    """Soft-delete a tracked contact"""
    contact = find_contact(name)
    if not contact:
        raise UsageError(f"no contact matching '{name}'")
    now = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute(
            "UPDATE contacts SET deleted_at = ? WHERE id = ?",
            (now, contact.id),
        )
    print(f"✗ {contact.name}")

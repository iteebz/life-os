"""Contact context — user notes about senders for Claude to consider."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

CONTACTS_PATH = Path.home() / ".comms" / "contacts.md"
PEEPS_DIR = Path.home() / "life" / "peeps"


@dataclass
class ContactNote:
    pattern: str
    tags: list[str]
    notes: str
    high_priority: bool = False


def _parse_md_contacts(path: Path) -> list[ContactNote]:
    contacts = []
    current_pattern = None
    current_tags: list[str] = []
    current_notes: list[str] = []

    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue

        if line.startswith("## "):
            if current_pattern:
                contacts.append(
                    ContactNote(
                        pattern=current_pattern,
                        tags=current_tags,
                        notes="\n".join(current_notes).strip(),
                    )
                )
            current_pattern = line[3:].strip()
            current_tags = []
            current_notes = []
        elif line.startswith("tags:"):
            tag_str = line[5:].strip()
            current_tags = [t.strip() for t in tag_str.split(",") if t.strip()]
        elif current_pattern:
            current_notes.append(line)

    if current_pattern:
        contacts.append(
            ContactNote(
                pattern=current_pattern,
                tags=current_tags,
                notes="\n".join(current_notes).strip(),
            )
        )

    return contacts


def _load_peeps() -> list[ContactNote]:
    if not PEEPS_DIR.exists():
        return []

    contacts = []
    for peep_file in PEEPS_DIR.glob("*.md"):
        try:
            text = peep_file.read_text()
            lines = text.splitlines()

            name = peep_file.stem.capitalize()
            notes_lines: list[str] = []
            tags: list[str] = []

            for line in lines:
                line = line.strip()
                if not line or line.startswith("# "):
                    continue
                if line.startswith("tags:"):
                    tags = [t.strip() for t in line[5:].split(",") if t.strip()]
                elif line.startswith("- ") or (line and not line.startswith("#")):
                    notes_lines.append(line.lstrip("- "))

            contacts.append(
                ContactNote(
                    pattern=name,
                    tags=tags,
                    notes=" ".join(notes_lines[:3]),
                    high_priority=True,
                )
            )
        except (OSError, ValueError):
            continue

    return contacts


def _load_contacts() -> list[ContactNote]:
    contacts = []

    if CONTACTS_PATH.exists():
        contacts.extend(_parse_md_contacts(CONTACTS_PATH))

    contacts.extend(_load_peeps())

    return contacts


def _match_sender(pattern: str, sender: str) -> bool:
    sender_lower = sender.lower()
    pattern_lower = pattern.lower()

    if "@" in pattern_lower:
        return pattern_lower in sender_lower

    if pattern_lower.startswith("*"):
        return sender_lower.endswith(pattern_lower[1:])

    return pattern_lower in sender_lower


def get_contact_context(sender: str) -> ContactNote | None:
    contacts = _load_contacts()
    for contact in contacts:
        if _match_sender(contact.pattern, sender):
            return contact
    return None


def get_all_contacts() -> list[ContactNote]:
    return _load_contacts()


def get_high_priority_patterns() -> list[str]:
    return [c.pattern.lower() for c in _load_contacts() if c.high_priority]


def format_contacts_for_prompt() -> str:
    contacts = _load_contacts()
    if not contacts:
        return ""

    lines = ["CONTACT CONTEXT (your notes about specific senders):"]

    priority = [c for c in contacts if c.high_priority]
    regular = [c for c in contacts if not c.high_priority]

    if priority:
        lines.append("HIGH PRIORITY (flag, never auto-archive):")
        for c in priority:
            tag_str = f" [{', '.join(c.tags)}]" if c.tags else ""
            lines.append(f"- {c.pattern}{tag_str}: {c.notes}")

    if regular:
        lines.append("Other contacts:")
        for c in regular:
            tag_str = f" [{', '.join(c.tags)}]" if c.tags else ""
            lines.append(f"- {c.pattern}{tag_str}: {c.notes}")

    return "\n".join(lines)

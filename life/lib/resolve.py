from pathlib import Path

from life.lib.frontmatter import parse as fm_parse

_PEOPLE_DIR = Path.home() / "life" / "steward" / "people"


def resolve_people_field(name: str, field: str) -> str | None:
    """Look up a field from people frontmatter by name or filename stem."""
    if not _PEOPLE_DIR.exists():
        return None
    name_lower = name.lower()
    for profile in _PEOPLE_DIR.glob("*.md"):
        text = profile.read_text()
        fm = fm_parse(text)
        if not fm:
            continue
        value = fm.get(field)
        if not value:
            continue
        if profile.stem.lower() == name_lower:
            return value
        name_val = fm.get("name", "")
        if name_val.lower() == name_lower:
            return value
    return None

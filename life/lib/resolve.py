import re
from pathlib import Path

import yaml

_PEOPLE_DIR = Path.home() / "life" / "steward" / "people"


def resolve_people_field(name: str, field: str) -> str | None:
    """Look up a field from people YAML frontmatter by name or filename stem."""
    if not _PEOPLE_DIR.exists():
        return None
    name_lower = name.lower()
    for profile in _PEOPLE_DIR.glob("*.md"):
        text = profile.read_text()
        match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
        if not match:
            continue
        try:
            frontmatter = yaml.safe_load(match.group(1))
        except Exception:  # noqa: S112
            continue
        if not isinstance(frontmatter, dict):
            continue
        value = frontmatter.get(field)
        if not value:
            continue
        if profile.stem.lower() == name_lower:
            return str(value)
        name_field = frontmatter.get("name", "")
        if isinstance(name_field, str) and name_field.lower() == name_lower:
            return str(value)
    return None

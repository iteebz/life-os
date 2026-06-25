import os
import tomllib
from pathlib import Path


def _tags_path() -> Path:
    life_dir = os.environ.get("LIFE_DIR", str(Path.home() / ".life"))
    return Path(life_dir) / "tags.toml"


def _load_tags_toml() -> dict[str, object]:
    path = _tags_path()
    if not path.exists():
        return {}
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


def load_tag_overrides() -> dict[str, str]:
    data = _load_tags_toml()
    return {k: v for k, v in data.items() if isinstance(v, str)}


def load_tag_groups() -> list[tuple[str, str]]:
    """Load ordered tag → label groups from [groups] in tags.toml."""
    data = _load_tags_toml()
    groups = data.get("groups")
    if not isinstance(groups, dict):
        return []
    return [(k, v) for k, v in groups.items() if isinstance(k, str) and isinstance(v, str)]


def load_valid_tags() -> frozenset[str] | None:
    """Return the valid tag set if tags.toml defines one, else None (open)."""
    data = _load_tags_toml()
    valid = data.get("valid")
    if not isinstance(valid, list):
        return None
    return frozenset(str(t).lower() for t in valid)


def validate_tag(tag: str) -> None:
    """Raise ValueError if tag is not in the valid set (when a valid set exists)."""
    valid = load_valid_tags()
    if valid is not None and tag.lower() not in valid:
        raise ValueError(f"unknown tag '{tag}' — not in tags.toml valid list")

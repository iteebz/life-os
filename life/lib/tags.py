import tomllib
from functools import lru_cache
from pathlib import Path

_TAGS_PATH = Path.home() / ".life" / "tags.toml"


@lru_cache(maxsize=1)
def _load_tags_toml() -> dict[str, object]:
    if not _TAGS_PATH.exists():
        return {}
    try:
        with _TAGS_PATH.open("rb") as f:
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

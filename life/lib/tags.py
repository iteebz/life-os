import tomllib
from functools import lru_cache
from pathlib import Path

_TAGS_PATH = Path.home() / ".life" / "tags.toml"


@lru_cache(maxsize=1)
def load_tag_overrides() -> dict[str, str]:
    """Load tag → color-name overrides from ~/.life/tags.toml."""
    if not _TAGS_PATH.exists():
        return {}
    try:
        with _TAGS_PATH.open("rb") as f:
            data = tomllib.load(f)
        return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}
    except Exception:
        return {}

from pathlib import Path

import yaml

LIFE_DIR = Path.home() / ".life"
DB_PATH = LIFE_DIR / "life.db"
CONFIG_PATH = LIFE_DIR / "config.yaml"
BACKUP_DIR = Path.home() / ".life_backups"


class Config:
    """Single-instance config manager. Load once, cache in memory."""

    _instance: "Config | None" = None
    _data: dict[str, object]

    def __new__(cls) -> "Config":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._data = {}
            cls._instance._load()
        return cls._instance

    def _load(self) -> None:
        """Load config from disk."""
        if not CONFIG_PATH.exists():
            self._data = {}
            return
        try:
            with CONFIG_PATH.open() as f:
                self._data = yaml.safe_load(f) or {}
        except Exception:
            self._data = {}

    def _save(self) -> None:
        """Persist config to disk."""
        LIFE_DIR.mkdir(exist_ok=True)
        with CONFIG_PATH.open("w") as f:
            yaml.dump(self._data, f, default_flow_style=False, allow_unicode=True)

    def get(self, key: str, default: object = None) -> object:
        """Get config value."""
        return self._data.get(key, default)

    def set(self, key: str, value: object) -> None:
        """Set config value and persist."""
        self._data[key] = value
        self._save()


_config = Config()


def get_partner_tag() -> str | None:
    """Get the tag used to track partner-facing tasks (e.g. 'janice'). None = disabled."""
    val = _config.get("partner_tag")
    return str(val).strip() if val else None


def get_profile() -> str:
    """Get current profile"""
    profile = _config.get("profile", "")
    return str(profile).strip() if profile else ""


def set_profile(profile: str) -> None:
    """Set current profile"""
    _config.set("profile", profile)


def get_dates() -> list[dict[str, str]]:
    """Get list of dates from config."""
    val = _config.get("dates")
    return val if isinstance(val, list) else []


def add_date(name: str, date: str, emoji: str = "📌") -> None:
    """Add a date to config."""
    val = _config.get("dates")
    dates: list[dict[str, str]] = val if isinstance(val, list) else []
    dates.append({"name": name, "date": date, "emoji": emoji})
    _config.set("dates", dates)


def remove_date(name: str) -> None:
    """Remove a date from config."""
    val = _config.get("dates")
    dates: list[dict[str, str]] = val if isinstance(val, list) else []
    filtered = [d for d in dates if d.get("name") != name]
    _config.set("dates", filtered)

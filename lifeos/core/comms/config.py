from pathlib import Path
from typing import Any, ClassVar

import yaml

LIFE_DIR = Path.home() / ".life"
COMMS_DIR = LIFE_DIR / "comms"
DB_PATH = LIFE_DIR / "life.db"
CONFIG_PATH = COMMS_DIR / "config.yaml"
RULES_PATH = COMMS_DIR / "rules.md"
BACKUP_DIR = Path.home() / ".life_backups"


class Config:
    _instance: ClassVar["Config | None"] = None
    _data: ClassVar[dict[str, Any]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            Config._data = {}
            cls._instance._load()
        return cls._instance

    def _load(self):
        if not CONFIG_PATH.exists():
            Config._data = {}
            return
        try:
            with CONFIG_PATH.open() as f:
                Config._data = yaml.safe_load(f) or {}
        except Exception:
            Config._data = {}

    def _save(self):
        COMMS_DIR.mkdir(parents=True, exist_ok=True)
        with CONFIG_PATH.open("w") as f:
            yaml.dump(self._data, f, default_flow_style=False, allow_unicode=True)

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value) -> None:
        self._data[key] = value
        self._save()


_config = Config()


def get_accounts(service_type: str | None = None) -> dict[str, Any] | list[Any]:
    accounts: dict[str, Any] = _config.get("accounts", {}) or {}
    if service_type:
        return accounts.get(service_type, [])
    return accounts


def add_account(service_type: str, account_data: dict[str, Any]) -> None:
    accounts: dict[str, Any] = _config.get("accounts", {}) or {}
    if service_type not in accounts:
        accounts[service_type] = []
    accounts[service_type].append(account_data)
    _config.set("accounts", accounts)

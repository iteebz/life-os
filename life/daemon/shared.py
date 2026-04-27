"""Daemon-wide constants and logging."""

import time
from pathlib import Path

from life.config import LIFE_DIR

DAEMON_DIR = LIFE_DIR
LOG_FILE = DAEMON_DIR / "daemon.log"

TG_SESSION_TIMEOUT = 3300  # 55 min — restart with boot after this
TG_SESSION_MAX_CHARS = 100_000  # ~33k tokens
MAX_TG_SPAWNS_PER_HOUR = 12
PEOPLE_DIR = Path.home() / "life" / "steward" / "people"


DAEMON_START_TIME: float = 0.0


def log(msg: str) -> None:
    DAEMON_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    entry = f"{timestamp} {msg}\n"
    with LOG_FILE.open("a") as f:
        f.write(entry)

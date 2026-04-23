"""Daemon-wide constants and logging."""

import time
from pathlib import Path

from life.config import LIFE_DIR

DAEMON_DIR = LIFE_DIR
LOG_FILE = DAEMON_DIR / "daemon.log"

TG_SESSION_TIMEOUT = 3600  # 1 hour — restart with boot after this
TG_SESSION_MAX_CHARS = 300_000  # ~100k tokens
MAX_TG_SPAWNS_PER_HOUR = 12
NUDGE_HOUR = 8
PEOPLE_DIR = Path.home() / "life" / "steward" / "people"


def log(msg: str) -> None:
    DAEMON_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    entry = f"{timestamp} {msg}\n"
    with LOG_FILE.open("a") as f:
        f.write(entry)

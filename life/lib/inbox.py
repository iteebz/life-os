import time
from pathlib import Path

INBOX_FILE = Path.home() / ".life" / "steward" / "inbox"


def write_inbox(channel: str, sender: str, body: str) -> None:
    INBOX_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%H:%M")
    entry = f"[{ts}] [{channel}] {sender}: {body}\n"
    with INBOX_FILE.open("a") as f:
        f.write(entry)


def clear_inbox() -> None:
    INBOX_FILE.unlink(missing_ok=True)


def pending_inbox() -> str:
    if not INBOX_FILE.exists():
        return ""
    content = INBOX_FILE.read_text().strip()
    clear_inbox()
    return content

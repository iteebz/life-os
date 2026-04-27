import contextlib
import time
from pathlib import Path

from life.lib.store import get_db

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


def mark_read_for_session(chat_id: int) -> None:
    with contextlib.suppress(Exception), get_db() as conn:
        conn.execute(
            "UPDATE events SET payload = json_set(payload, '$.read_at', datetime('now')) "
            "WHERE kind = 'inbound' AND channel = 'telegram' "
            "AND json_extract(payload, '$.read_at') IS NULL "
            "AND peer_id IN ("
            "  SELECT pa.peer_id FROM peer_addresses pa "
            "  WHERE pa.channel = 'telegram' AND pa.address = ?"
            ")",
            (str(chat_id),),
        )

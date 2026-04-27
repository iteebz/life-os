"""Inbound message handler — wake or notify steward on new messages.

When a message arrives from any channel:
1. Active interactive session? → notify via hook (write to inbox file)
2. No active session, within rollover limits? → continue last session
3. No active session, stale? → start fresh session
4. Quiet hours? → queue for morning

The daemon thread calls handle() for each inbound message.
Steward reads the inbox file via a UserPromptSubmit hook.
"""

import time
from pathlib import Path

from life.daemon.shared import TG_SESSION_MAX_CHARS, TG_SESSION_TIMEOUT, log
from life.lib.store import get_db

INBOX_FILE = Path.home() / ".life" / "steward" / "inbox"


def _active_spawn() -> dict | None:
    """Check if there's an active steward spawn (chat or tg)."""
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT id, mode, source, started_at, session_id FROM spawns "
                "WHERE status = 'active' ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "mode": row[1],
            "source": row[2],
            "started_at": row[3],
            "session_id": row[4],
        }
    except Exception:
        return None


def _session_age_seconds(spawn: dict) -> float:
    """How old is the current spawn in seconds."""
    from datetime import datetime

    try:
        started = datetime.fromisoformat(spawn["started_at"])
        return (datetime.now() - started).total_seconds()
    except Exception:
        return 0


def _session_chars(session_id: int | None) -> int:
    """Total chars in the current session's messages."""
    if not session_id:
        return 0
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(LENGTH(body)), 0) FROM messages "
                "WHERE channel = 'chat' AND peer = ?",
                (str(session_id),),
            ).fetchone()
        return row[0] if row else 0
    except Exception:
        return 0


def _write_inbox(channel: str, sender: str, body: str) -> None:
    """Write to inbox file for active session to pick up via hook."""
    INBOX_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%H:%M")
    entry = f"[{ts}] [{channel}] {sender}: {body}\n"
    with INBOX_FILE.open("a") as f:
        f.write(entry)


def _clear_inbox() -> None:
    INBOX_FILE.unlink(missing_ok=True)


def _should_rollover(spawn: dict) -> bool:
    """Check if current session exceeds time or char limits."""
    age = _session_age_seconds(spawn)
    chars = _session_chars(spawn.get("session_id"))
    return age > TG_SESSION_TIMEOUT or chars > TG_SESSION_MAX_CHARS


def handle(channel: str, sender: str, body: str, chat_id: int | None = None) -> str:
    """Handle an inbound message. Returns action taken.

    Actions: 'notified', 'woke', 'spawned', 'queued', 'responded'
    """
    from life.nudge import is_quiet_now

    if is_quiet_now():
        log(f"[inbound] quiet hours — queueing {channel} from {sender}")
        _write_inbox(channel, sender, body)
        return "queued"

    spawn = _active_spawn()

    if spawn and spawn["mode"] == "chat":
        if _should_rollover(spawn):
            log("[inbound] active session over limits — will start fresh")
            # Don't kill the session — let it finish. Queue the message.
            _write_inbox(channel, sender, body)
            return "queued"

        # Active interactive session — notify via inbox
        _write_inbox(channel, sender, body)
        log(f"[inbound] notified active session (spawn {spawn['id']})")
        return "notified"

    # No active interactive session — respond via stateless spawn + queue for next session
    if channel == "telegram" and chat_id is not None:
        from life.comms.messages import telegram as tg
        from life.daemon.session import build_reply_prompt, load_history_from_db
        from life.daemon.spawn import fetch_wake_context, spawn_claude

        history = load_history_from_db(chat_id)
        if history:
            prompt = build_reply_prompt(history, body)
        else:
            from life.daemon.run import _build_tg_boot_prompt

            context = fetch_wake_context()
            prompt = _build_tg_boot_prompt(body, sender, context)

        response = spawn_claude(prompt)
        tg.send(chat_id, response)
        log(f"[inbound] responded via telegram ({len(response)} chars)")
        return "responded"

    # Non-telegram or no chat_id — queue for next session
    _write_inbox(channel, sender, body)
    log(f"[inbound] queued {channel} message from {sender}")
    return "queued"


def pending_inbox() -> str:
    """Read and clear the inbox. Called by steward on wake or via hook."""
    if not INBOX_FILE.exists():
        return ""
    content = INBOX_FILE.read_text().strip()
    _clear_inbox()
    return content

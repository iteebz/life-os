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
from datetime import datetime
from pathlib import Path

from life.comms.messages import telegram as tg
from life.daemon.session import build_reply_prompt, build_tg_boot_prompt, load_history_from_db
from life.daemon.shared import TG_SESSION_MAX_CHARS, TG_SESSION_TIMEOUT, log
from life.daemon.spawn import fetch_wake_context, spawn_claude
from life.lib.clock import is_quiet_now
from life.lib.store import get_db

INBOX_FILE = Path.home() / ".life" / "steward" / "inbox"
# Cache TTL is 60m. Resume within this window = cached context = fast + cheap.
# 55m gives 5m buffer before cache dies.
WARM_AGE_SECONDS = 3300
WARM_MAX_CHARS = 100_000


def _active_spawn() -> dict[str, str | int | None] | None:
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


def _session_age_seconds(spawn: dict[str, str | int | None]) -> float:
    """How old is the current spawn in seconds."""
    try:
        started_at = spawn["started_at"]
        if not isinstance(started_at, str):
            return 0
        started = datetime.fromisoformat(started_at)
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


def _warm_session() -> tuple[str, int] | None:
    """Find the most recent chat session that's warm enough to resume.

    Returns (claude_session_id, db_session_id) or None.
    Warm = closed cleanly + last activity <55m + accumulated chars <100k.
    """
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT s.claude_session_id, s.id, s.logged_at "
                "FROM sessions s "
                "JOIN spawns sp ON sp.session_id = s.id "
                "WHERE sp.mode = 'chat' AND sp.status = 'complete' "
                "AND s.claude_session_id IS NOT NULL "
                "ORDER BY sp.ended_at DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        claude_id, db_id, _logged_at = row
        chars = _session_chars(db_id)
        if chars > WARM_MAX_CHARS:
            return None
        # Use most recent spawn end as activity proxy
        with get_db() as conn:
            end_row = conn.execute(
                "SELECT MAX(ended_at) FROM spawns WHERE session_id = ?",
                (db_id,),
            ).fetchone()
        if not end_row or not end_row[0]:
            return None
        last_active = datetime.fromisoformat(end_row[0])
        age = (datetime.now() - last_active).total_seconds()
        if age > WARM_AGE_SECONDS:
            return None
        return claude_id, db_id
    except Exception:
        return None


def _should_rollover(spawn: dict[str, str | int | None]) -> bool:
    """Check if current session exceeds time or char limits."""
    age = _session_age_seconds(spawn)
    raw_id = spawn.get("session_id")
    chars = _session_chars(int(raw_id) if isinstance(raw_id, int) else None)
    return age > TG_SESSION_TIMEOUT or chars > TG_SESSION_MAX_CHARS


def handle(channel: str, sender: str, body: str, chat_id: int | None = None) -> str:
    """Handle an inbound message. Returns action taken.

    Actions: 'notified', 'woke', 'spawned', 'queued', 'responded'
    """
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

    # No active interactive session — try resuming a warm one, else stateless
    if channel == "telegram" and chat_id is not None:
        warm = _warm_session()
        if warm:
            claude_id, db_id = warm
            log(f"[inbound] resuming warm session {db_id} ({claude_id[:8]})")
            response = spawn_claude(body, resume_session_id=claude_id)
            tg.send(chat_id, response)
            return "resumed"

        history = load_history_from_db(chat_id)
        if history:
            prompt = build_reply_prompt(history, body)
        else:
            context = fetch_wake_context()
            prompt = build_tg_boot_prompt(body, sender, context)

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

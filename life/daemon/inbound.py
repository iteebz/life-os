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
from datetime import datetime, timezone
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
        started = datetime.fromisoformat(started_at).replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - started).total_seconds()
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
        last_active = datetime.fromisoformat(end_row[0]).replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - last_active).total_seconds()
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

    Actions: 'notified', 'queued', 'resumed', 'responded'.
    Writes a corresponding event row referencing the latest inbound event
    for (channel, address) for coverage instrumentation.
    """
    started_ms = time.time() * 1000
    address = str(chat_id) if channel == "telegram" and chat_id is not None else sender

    def _emit(action: str, error: str | None = None, spawn_id: int | None = None) -> None:
        from life.comms import events
        from life.comms.peers import resolve_or_create

        try:
            peer_id = resolve_or_create(channel, address, sender)
            ref_id = _latest_inbound_event(channel, address)
            payload = {
                "sender": sender,
                "preview": body[:120],
                "latency_ms": int(time.time() * 1000 - started_ms),
            }
            if error:
                payload["error"] = error
            events.record(
                action,
                peer_id=peer_id,
                channel=channel,
                ref_id=ref_id,
                spawn_id=spawn_id,
                payload=payload,
            )
        except Exception as e:
            log(f"[inbound] event record failed: {e}")

    if is_quiet_now():
        log(f"[inbound] quiet hours — queueing {channel} from {sender}")
        _write_inbox(channel, sender, body)
        _emit("queued", error="quiet_hours")
        return "queued"

    spawn = _active_spawn()

    if spawn and spawn["mode"] == "chat":
        if _should_rollover(spawn):
            log("[inbound] active session over limits — will start fresh")
            _write_inbox(channel, sender, body)
            _emit("queued", error="rollover")
            return "queued"

        _write_inbox(channel, sender, body)
        log(f"[inbound] notified active session (spawn {spawn['id']})")
        spawn_id_raw = spawn.get("id")
        _emit("notified", spawn_id=int(spawn_id_raw) if isinstance(spawn_id_raw, int) else None)
        return "notified"

    if channel == "telegram" and chat_id is not None:
        warm = _warm_session()
        if warm:
            claude_id, db_id = warm
            log(f"[inbound] resuming warm session {db_id} ({claude_id[:8]})")
            response = spawn_claude(body, resume_session_id=claude_id)
            tg.send(chat_id, response)
            _emit("resumed")
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
        _emit("responded")
        return "responded"

    _write_inbox(channel, sender, body)
    log(f"[inbound] queued {channel} message from {sender}")
    _emit("queued", error="no_chat_id")
    return "queued"


def _latest_inbound_event(channel: str, address: str) -> int | None:
    """Find the most recent inbound event id for (channel, address)."""
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT e.id FROM events e "
                "JOIN peer_addresses pa ON pa.peer_id = e.peer_id "
                "WHERE e.kind = 'inbound' AND e.channel = ? "
                "AND pa.channel = ? AND pa.address = ? "
                "ORDER BY e.id DESC LIMIT 1",
                (channel, channel, str(address)),
            ).fetchone()
        return row[0] if row else None
    except Exception:
        return None


def pending_inbox() -> str:
    """Read and clear the inbox. Called by steward on wake or via hook."""
    if not INBOX_FILE.exists():
        return ""
    content = INBOX_FILE.read_text().strip()
    _clear_inbox()
    return content


def catch_up(chat_id: int) -> str:
    """Process unread inbound telegram messages on daemon start.

    Queries messages table for inbound telegram messages with read_at IS NULL,
    batches them into a single steward spawn, marks them read, and replies.
    Returns action: 'caught_up' or 'nothing'.
    """
    try:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT id, peer_name, body, timestamp FROM messages "
                "WHERE channel = 'telegram' AND direction = 'in' "
                "AND read_at IS NULL AND peer = ? "
                "ORDER BY timestamp ASC",
                (str(chat_id),),
            ).fetchall()
    except Exception:
        return "nothing"

    if not rows:
        return "nothing"

    msg_ids = [r[0] for r in rows]
    lines = []
    for r in rows:
        ts = time.strftime("%H:%M %b %d", time.localtime(r[3])) if r[3] else "?"
        lines.append(f"[{ts}] {r[1] or 'unknown'}: {r[2]}")

    batch = "\n".join(lines)
    context = fetch_wake_context()
    prompt = (
        f"You are Steward responding via Telegram after being offline.\n\n"
        f"Current life state:\n{context}\n\n"
        f"While you were offline, {len(rows)} message(s) arrived:\n\n{batch}\n\n"
        f"Respond to what needs a response. Acknowledge what doesn't. "
        f"Start with 🌱. Short and actionable."
    )

    log(f"[catch-up] {len(rows)} unread message(s), spawning steward")
    response = spawn_claude(prompt)
    tg.send(chat_id, response)

    _mark_read(msg_ids)
    log(f"[catch-up] responded ({len(response)} chars), marked {len(msg_ids)} read")
    return "caught_up"


def mark_read_for_session(chat_id: int) -> None:
    """Mark all inbound messages as read for a chat. Called after live handling."""
    try:
        with get_db() as conn:
            conn.execute(
                "UPDATE messages SET read_at = datetime('now') "
                "WHERE channel = 'telegram' AND direction = 'in' "
                "AND read_at IS NULL AND peer = ?",
                (str(chat_id),),
            )
    except Exception:
        pass


def _mark_read(msg_ids: list[str]) -> None:
    if not msg_ids:
        return
    try:
        with get_db() as conn:
            placeholders = ",".join("?" for _ in msg_ids)
            conn.execute(
                f"UPDATE messages SET read_at = datetime('now') "  # noqa: S608
                f"WHERE id IN ({placeholders})",
                msg_ids,
            )
    except Exception:
        pass

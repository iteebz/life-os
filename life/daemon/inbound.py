"""Inbound message handler — route to current steward session.

Routing:
1. Hookable session (cli with live pid)? → message already in db, hook drains.
2. Resumable session (active/idle within warm window)? → resume turn.
3. Neither? → spawn fresh session.
"""

import contextlib
import time

from life.comms import events
from life.comms.messages import telegram as tg
from life.comms.peers import resolve_or_create
from life.daemon.session import build_reply_prompt, build_tg_boot_prompt, load_history_from_db
from life.daemon.shared import log
from life.daemon.spawn import fetch_wake_context, spawn_claude
from life.lib.clock import is_quiet_now
from life.lib.store import get_db
from life.steward import create_session, current_session, hookable_session, set_session_idle, touch_session


def handle(channel: str, sender: str, body: str, chat_id: int | None = None) -> str:
    """Handle an inbound message. Returns action taken."""
    started_ms = time.time() * 1000
    address = str(chat_id) if channel == "telegram" and chat_id is not None else sender

    def _emit(action: str, error: str | None = None, session_id: int | None = None) -> None:
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
                session_id=session_id,
                payload=payload,
            )
        except Exception as e:
            log(f"[inbound] event record failed: {e}")

    if is_quiet_now():
        log(f"[inbound] quiet hours — queueing {channel} from {sender}")
        _emit("queued", error="quiet_hours")
        return "queued"

    # 1. Hookable session (cli window open)?
    hooked = hookable_session()
    if hooked:
        log(f"[inbound] notified hookable session {hooked.id}")
        _emit("notified", session_id=hooked.id)
        return "notified"

    # 2. Resumable session?
    current = current_session()
    if current and current.claude_session_id and channel == "telegram" and chat_id is not None:
        log(f"[inbound] resuming session {current.id} ({current.claude_session_id[:8]})")
        touch_session(current.id)
        response = spawn_claude(body, resume_session_id=current.claude_session_id)
        tg.send(chat_id, response)
        set_session_idle(current.id)
        _emit("resumed", session_id=current.id)
        return "resumed"

    # 3. Fresh session
    if channel == "telegram" and chat_id is not None:
        history = load_history_from_db(chat_id)
        if history:
            prompt = build_reply_prompt(history, body)
        else:
            context = fetch_wake_context()
            prompt = build_tg_boot_prompt(body, sender, context)

        db_sid = create_session(
            summary=f"(tg) {sender}",
            source="tg",
            name=f"tg {sender}",
        )
        response = spawn_claude(prompt)
        tg.send(chat_id, response)
        set_session_idle(db_sid)
        log(f"[inbound] new session {db_sid}, responded ({len(response)} chars)")
        _emit("responded", session_id=db_sid)
        return "responded"

    log(f"[inbound] queued {channel} message from {sender}")
    _emit("queued", error="no_chat_id")
    return "queued"


def _latest_inbound_event(channel: str, address: str) -> int | None:
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


def catch_up(chat_id: int) -> str:
    """Process unread inbound telegram messages on daemon start."""
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

    sid = create_session(
        summary=f"(catch-up) {len(rows)} msgs",
        source="daemon",
        name="catch-up",
    )
    log(f"[catch-up] {len(rows)} unread message(s), session {sid}")
    response = spawn_claude(prompt)
    tg.send(chat_id, response)
    set_session_idle(sid)

    _mark_read(msg_ids)
    log(f"[catch-up] responded ({len(response)} chars), marked {len(msg_ids)} read")
    return "caught_up"


def _mark_read(msg_ids: list[str]) -> None:
    if not msg_ids:
        return
    with contextlib.suppress(Exception), get_db() as conn:
        placeholders = ",".join("?" for _ in msg_ids)
        conn.execute(
            f"UPDATE events SET payload = json_set(payload, '$.read_at', datetime('now')) "  # noqa: S608
            f"WHERE kind = 'inbound' "
            f"AND json_extract(payload, '$.raw_id') IN ({placeholders})",
            msg_ids,
        )

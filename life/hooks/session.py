"""Session row management, turn logging, and context-window meta."""

import contextlib
import os
import time
from datetime import UTC, datetime

from life.comms import events
from lifeos.core.config import get_user_name
from lifeos.core.lib.store import get_db

CTX_MAX_CHARS = 100_000
WRAP_THRESHOLD_SECONDS = 3300  # 55m


def db_session_id(provider_session_id: str) -> int | None:
    if provider_session_id.isdigit():
        return int(provider_session_id)
    with contextlib.suppress(Exception):
        with get_db() as conn:
            row = conn.execute(
                "SELECT id FROM sessions WHERE provider_session_id = ? ORDER BY id DESC LIMIT 1",
                (provider_session_id,),
            ).fetchone()
            return row[0] if row else None
    return None


def log_turn(direction: str, body: str, session_id: str) -> None:
    if len(body) > 10000:
        body = body[:10000] + f"\n... [{len(body) - 10000} chars truncated]"
    ts = int(time.time())
    msg_id = f"chat-{session_id[:8]}-{ts}-{direction}"
    peer_name = get_user_name() if direction == "in" else "steward"
    db_sid = db_session_id(session_id)
    with contextlib.suppress(Exception):
        events.record_message(
            channel="chat",
            address=session_id,
            direction=direction,
            body=body,
            timestamp=ts,
            raw_id=msg_id,
            peer_name=peer_name,
            sent_by=peer_name,
            session_id=db_sid,
        )


def ensure_session_row(provider_session_id: str) -> None:
    if provider_session_id == "unknown" or os.environ.get("STEWARD_DB_SESSION_ID"):
        return

    steward_sid = os.environ.get("STEWARD_SESSION_ID", "")
    if steward_sid.isdigit():
        with contextlib.suppress(Exception):
            with get_db() as conn:
                conn.execute(
                    "UPDATE sessions SET provider_session_id = ?, state = 'active', "
                    "last_active_at = STRFTIME('%Y-%m-%dT%H:%M:%S', 'now', 'localtime') "
                    "WHERE id = ? AND provider_session_id IS NULL",
                    (provider_session_id, int(steward_sid)),
                )
        return

    name = os.environ.get("STEWARD_SESSION_NAME") or provider_session_id[:8]
    model = os.environ.get("STEWARD_SESSION_MODEL")
    source = os.environ.get("STEWARD_SESSION_SOURCE", "cli")
    with contextlib.suppress(Exception):
        with get_db() as conn:
            row = conn.execute(
                "SELECT id FROM sessions WHERE provider_session_id = ?",
                (provider_session_id,),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE sessions SET state = 'active', "
                    "last_active_at = STRFTIME('%Y-%m-%dT%H:%M:%S', 'now', 'localtime') "
                    "WHERE id = ?",
                    (row[0],),
                )
                return
            conn.execute(
                "INSERT INTO sessions (summary, provider_session_id, name, model, source, "
                "state, started_at, last_active_at, pid) VALUES "
                "(?, ?, ?, ?, ?, 'active', "
                "STRFTIME('%Y-%m-%dT%H:%M:%S', 'now', 'localtime'), "
                "STRFTIME('%Y-%m-%dT%H:%M:%S', 'now', 'localtime'), ?)",
                (f"(active) {name}", provider_session_id, name, model, source, os.getppid()),
            )


def surface_session_meta(session_id: str) -> None:
    with contextlib.suppress(Exception):
        with get_db() as conn:
            row = conn.execute(
                "SELECT logged_at FROM sessions WHERE provider_session_id = ?",
                (session_id,),
            ).fetchone()
            if not row:
                return
            (logged_at,) = row
            char_row = conn.execute(
                "SELECT COALESCE(SUM(LENGTH(body)), 0) FROM messages WHERE channel = 'chat' AND peer = ?",
                (session_id,),
            ).fetchone()
            chars = char_row[0] if char_row else 0
        started = datetime.fromisoformat(logged_at).replace(tzinfo=UTC)
        age = int((datetime.now(UTC) - started).total_seconds())
        age_str = f"{age // 60}m" if age >= 60 else f"{age}s"
        nudge = ""
        if chars >= 100_000:
            nudge = '\n100k chars: sleep now. `steward sleep "..."`, commit, end the session.'
        elif chars >= 90_000:
            nudge = "\n90k chars: one more action then sleep."
        elif chars >= 80_000:
            nudge = "\n80k chars: wrap soon, no new threads."
        elif chars >= 70_000:
            nudge = "\n70k chars: close open topics, avoid new ones."
        elif chars >= 60_000:
            nudge = "\n60k chars: start wrapping up."
        elif chars >= 50_000:
            nudge = "\n50k chars: halfway — wrap up side threads."
        elif age >= WRAP_THRESHOLD_SECONDS:
            nudge = "\nsession is long: consider closing soon."
        if nudge or chars >= 50_000:
            print(f"\n<session-meta>session: {age_str} elapsed, {chars:,} / 100k chars{nudge}\n</session-meta>")


def auto_sleep_summary(session_id: str) -> str:
    with contextlib.suppress(Exception):
        with get_db() as conn:
            row = conn.execute(
                "SELECT id FROM sessions WHERE provider_session_id = ? ORDER BY id DESC LIMIT 1",
                (session_id,),
            ).fetchone()
            if not row:
                return "auto-closed (no session record)"
            db_id = row[0]
            msgs = conn.execute(
                "SELECT direction, body FROM messages WHERE channel = 'chat' AND peer = ? ORDER BY logged_at DESC LIMIT 10",
                (str(db_id),),
            ).fetchall()
        if not msgs:
            return "auto-closed (no messages)"
        human_msgs = [m[1][:120] for m in msgs if m[0] == "in"]
        last_out = next((m[1][:200] for m in msgs if m[0] == "out"), None)
        parts = []
        if human_msgs:
            parts.append(f"discussed: {' / '.join(human_msgs[:3])}")
        if last_out:
            parts.append(f"last: {last_out}")
        return " — ".join(parts) if parts else "auto-closed"
    return "auto-closed (summary failed)"

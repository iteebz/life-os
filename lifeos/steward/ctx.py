"""life steward ctx — show current session context window usage."""

import os
from datetime import datetime

from fncli import cli

from lifeos.core.lib.store import get_db
from lifeos.core.store.migrations import init

CTX_MAX_CHARS = 100_000


@cli("life")
@cli("life steward")
def ctx() -> None:
    """Show current session context window usage."""
    init()
    session_id = os.environ.get("STEWARD_SESSION_ID")
    if not session_id:
        print("no session ID (STEWARD_SESSION_ID not set)")
        return

    with get_db() as conn:
        # Try lookup by DB row ID (numeric) first
        if session_id.isdigit():
            row = conn.execute(
                "SELECT started_at, chat_id, provider_session_id FROM sessions WHERE id = ?",
                (int(session_id),),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT started_at, chat_id, provider_session_id FROM sessions WHERE provider_session_id = ?",
                (session_id,),
            ).fetchone()

        if not row:
            print(f"no session record for {session_id}")
            return

        started_at, chat_id, provider_session_id = row

        db_id: int | None = int(session_id) if session_id.isdigit() else None
        if db_id is None and provider_session_id:
            row2 = conn.execute(
                "SELECT id FROM sessions WHERE provider_session_id = ?", (provider_session_id,)
            ).fetchone()
            db_id = row2[0] if row2 else None

        if db_id is not None:
            char_row = conn.execute(
                "SELECT COALESCE(SUM(LENGTH(json_extract(payload, '$.body'))), 0) FROM events WHERE session_id = ?",
                (db_id,),
            ).fetchone()
        elif chat_id:
            try:
                started_ts = datetime.fromisoformat(started_at).timestamp()
            except Exception:
                started_ts = 0
            char_row = conn.execute(
                "SELECT COALESCE(SUM(LENGTH(body)), 0) FROM messages "
                "WHERE channel = 'telegram' AND peer = ? AND timestamp > ?",
                (str(chat_id), int(started_ts)),
            ).fetchone()
        elif provider_session_id:
            char_row = conn.execute(
                "SELECT COALESCE(SUM(LENGTH(body)), 0) FROM messages WHERE channel = 'chat' AND peer = ?",
                (provider_session_id,),
            ).fetchone()
        else:
            char_row = None

        chars = char_row[0] if char_row else 0

    try:
        started = datetime.fromisoformat(started_at)
        age = int((datetime.now() - started).total_seconds())
        age_str = f"{age // 60}m" if age >= 60 else f"{age}s"
    except Exception:
        age_str = "?"

    pct = int(chars / CTX_MAX_CHARS * 100)
    bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
    print(f"🌱 ctx [{bar}] {pct}%  {chars:,} / {CTX_MAX_CHARS:,} chars  ({age_str} elapsed)")

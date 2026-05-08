"""life steward ctx — show current session context usage."""

import contextlib
import os
from datetime import UTC, datetime

from fncli import cli

from life.lib.store import get_db
from life.store.migrations import init

CTX_MAX_CHARS = 100_000


@cli("life steward")
def ctx() -> None:
    """Show current session context window usage."""
    init()
    session_id = os.environ.get("STEWARD_SESSION_ID") or os.environ.get("CLAUDE_SESSION_ID")
    if not session_id:
        print("no session ID found (STEWARD_SESSION_ID not set)")
        return

    with contextlib.suppress(Exception):
        with get_db() as conn:
            row = conn.execute(
                "SELECT logged_at FROM sessions WHERE claude_session_id = ?",
                (session_id,),
            ).fetchone()
            if not row:
                print(f"no session record for {session_id[:8]}")
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
        pct = int(chars / CTX_MAX_CHARS * 100)
        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
        print(f"ctx [{bar}] {pct}%  {chars:,} / {CTX_MAX_CHARS:,} chars  ({age_str} elapsed)")
        return

    print("ctx: unavailable")

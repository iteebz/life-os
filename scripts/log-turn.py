#!/usr/bin/env python3
"""Claude Code hook script for steward sessions.

UserPromptSubmit: logs human prompt + surfaces inbox (new telegram/signal messages)
Stop: logs steward response

Usage: log-turn.py <direction>
  - direction: 'in' (human prompt) or 'out' (steward response)
  - Reads JSON from stdin
  - Session ID from STEWARD_SESSION_ID env
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from life.store.migrations import init
from life.lib.store import get_db

INBOX_FILE = Path.home() / ".life" / "steward" / "inbox"

WRAP_THRESHOLD_CHARS = 100_000   # ~33k tokens — wrap soon
SLEEP_THRESHOLD_CHARS = 150_000  # ~50k tokens — sleep now
WRAP_THRESHOLD_SECONDS = 3300    # 55m


def _log_message(direction: str, body: str, session_id: str) -> None:

    if len(body) > 10000:
        body = body[:10000] + f"\n... [{len(body) - 10000} chars truncated]"

    init()
    ts = int(time.time())
    msg_id = f"chat-{session_id[:8]}-{ts}-{direction}"

    try:
        with get_db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO messages "
                "(id, channel, direction, peer, peer_name, body, timestamp) "
                "VALUES (?, 'chat', ?, ?, ?, ?, ?)",
                (msg_id, direction, session_id, "tyson" if direction == "in" else "steward", body, ts),
            )
    except Exception:
        pass


def _surface_session_meta(session_id: str) -> None:
    """Inject session age + size + threshold nudges as context."""
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT id, logged_at FROM sessions WHERE claude_session_id = ?",
                (session_id,),
            ).fetchone()
            if not row:
                return
            db_id, logged_at = row
            char_row = conn.execute(
                "SELECT COALESCE(SUM(LENGTH(body)), 0) FROM messages "
                "WHERE channel = 'chat' AND peer = ?",
                (str(db_id),),
            ).fetchone()
            chars = char_row[0] if char_row else 0

        from datetime import datetime
        started = datetime.fromisoformat(logged_at)
        age = int((datetime.now() - started).total_seconds())
        age_str = f"{age // 60}m" if age >= 60 else f"{age}s"

        nudge = ""
        if chars >= SLEEP_THRESHOLD_CHARS:
            nudge = "\nsleep now: close one loop, run `steward sleep \"...\"`, commit, end the session."
        elif chars >= WRAP_THRESHOLD_CHARS:
            nudge = "\nwrap soon: prefer closing the open loop over starting new threads."
        elif age >= WRAP_THRESHOLD_SECONDS:
            nudge = "\nsession is long: consider closing soon."

        if nudge or chars > 50_000:
            print(f"\n<session-meta>session: {age_str} elapsed, {chars} chars logged{nudge}\n</session-meta>")
    except Exception:
        pass


def _surface_inbox() -> None:
    """Print pending inbox messages so claude sees them as context."""
    if not INBOX_FILE.exists():
        return
    content = INBOX_FILE.read_text().strip()
    if not content:
        return
    INBOX_FILE.unlink(missing_ok=True)
    # stdout from UserPromptSubmit hooks is injected as context
    print(f"\n[new messages received while you were working]\n{content}")


def main() -> None:
    if len(sys.argv) < 2:
        return

    direction = sys.argv[1]
    session_id = os.environ.get("STEWARD_SESSION_ID", "unknown")

    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return

    if direction == "in":
        body = data.get("prompt", "")
    else:
        body = data.get("response", "") or data.get("stopReason", "")

    if not body or not body.strip():
        return

    body = body.strip()
    _log_message(direction, body, session_id)

    # On human prompt, surface inbox + session meta
    if direction == "in":
        _surface_inbox()
        _surface_session_meta(session_id)


if __name__ == "__main__":
    main()

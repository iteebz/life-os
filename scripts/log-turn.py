#!/usr/bin/env python3
"""Log a chat turn to the messages table. Called by Claude Code hooks.

UserPromptSubmit: receives {"prompt": "..."} on stdin
Stop: receives {"stopReason": "...", "response": "..."} on stdin (response may not exist)

Usage: log-turn.py <direction>
  - direction: 'in' (human prompt) or 'out' (steward response)
  - Reads JSON from stdin
  - Session ID from CLAUDE_SESSION_ID env or 'unknown'
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from life.db import init
from life.lib.store import get_db


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


if __name__ == "__main__":
    main()

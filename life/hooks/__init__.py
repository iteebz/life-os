"""life hooks — context injection and git enforcement for steward sessions."""

import contextlib
import json
import os
import re
import sys
import time

from life.comms import events
from life.hooks.git import cmd_hook_commit, cmd_hook_pre_commit
from life.hooks.session import (
    auto_sleep_summary,
    ensure_session_row,
    log_turn,
    surface_session_meta,
)
from life.hooks.signals import ALL_SIGNALS, load_state, render_inbox, save_state
from lifeos.core.lib.store import get_db
from lifeos.core.store.migrations import init
from lifeos.steward.sleep import _push_repos


def cmd_hook_prompt() -> None:
    init()
    data = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    body = (data.get("prompt") or "").strip()
    if not body:
        return
    provider_sid = data.get("session_id") or os.environ.get("STEWARD_SESSION_ID", "unknown")
    ensure_session_row(provider_sid)
    log_turn("in", body, provider_sid)
    rows = events.drain_inbox()
    if rows:
        print("\n[new messages received while you were working]\n" + "\n".join(render_inbox(rows)))
    surface_session_meta(provider_sid)


def cmd_hook_stop() -> None:
    init()
    data = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    body = (data.get("response") or data.get("stopReason") or "").strip()
    if not body:
        return
    provider_sid = data.get("session_id") or os.environ.get("STEWARD_SESSION_ID", "unknown")
    log_turn("out", body, provider_sid)


def cmd_hook_post_tool() -> None:
    init()
    data = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    tool = data.get("tool_name", "")
    if tool != "Bash":
        return
    cmd = (data.get("tool_input") or {}).get("command", "")
    is_done = bool(re.search(r"\blife done\b", cmd))
    is_habit = bool(re.search(r"\blife habit\b.*\b(done|check)\b", cmd))
    if not is_done and not is_habit:
        return

    state = load_state()
    session_id = os.environ.get("STEWARD_SESSION_ID", "unknown")
    flag = f"win_broadcast_{session_id[:8]}"
    if state.get(flag):
        return
    state[flag] = "1"
    save_state(state)

    output = (data.get("tool_response") or {}).get("output", "").strip()
    kind = "task" if is_done else "habit"
    msg = f"win ({kind}): {cmd.strip()}"
    if output:
        msg += f" → {output[:80]}"
    with contextlib.suppress(Exception):
        events.record_message(
            channel="steward",
            address="broadcast",
            direction="out",
            body=msg,
            timestamp=int(time.time()),
            raw_id=f"win-{session_id[:8]}-{int(time.time())}",
            peer_name="steward",
            sent_by="steward",
        )


def cmd_hook_session_end() -> None:
    init()
    sys.stdin.read()
    session_id = os.environ.get("STEWARD_SESSION_ID", "unknown")
    if session_id == "unknown":
        return
    summary = auto_sleep_summary(session_id)
    with contextlib.suppress(Exception):
        with get_db() as conn:
            row = conn.execute(
                "SELECT id, state FROM sessions WHERE provider_session_id = ? ORDER BY id DESC LIMIT 1",
                (session_id,),
            ).fetchone()
            if row and row[1] != "closed":
                conn.execute(
                    "UPDATE sessions SET state = 'closed', summary = ?, "
                    "last_active_at = STRFTIME('%Y-%m-%dT%H:%M:%S', 'now', 'localtime') "
                    "WHERE id = ?",
                    (summary, row[0]),
                )
    with contextlib.suppress(Exception):
        _push_repos()


def cmd_hook_tool() -> None:
    init()
    sys.stdin.read()
    session_id = os.environ.get("STEWARD_SESSION_ID", "unknown")
    with contextlib.suppress(Exception):
        surface_session_meta(session_id)

    state = load_state()
    parts: list[str] = []
    for fn in ALL_SIGNALS:
        try:
            fn(state, parts)
        except Exception as e:
            parts.append(f"[hook signal {fn.__name__} failed: {e}]")
    save_state(state)

    if parts:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "additionalContext": "\n".join(parts),
                    }
                }
            ),
            end="",
        )


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "hook"]
    if not args:
        print("usage: life hook <event>", file=sys.stderr)
        sys.exit(1)
    dispatch = {
        "tool": cmd_hook_tool,
        "post-tool": cmd_hook_post_tool,
        "prompt": cmd_hook_prompt,
        "stop": cmd_hook_stop,
        "session-end": cmd_hook_session_end,
        "commit": cmd_hook_commit,
        "pre-commit": cmd_hook_pre_commit,
    }
    fn = dispatch.get(args[0])
    if fn is None:
        print(f"unknown hook event: {args[0]}", file=sys.stderr)
        sys.exit(1)
    fn()

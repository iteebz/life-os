"""life hook — context injection for steward spawns.

Mirrors space hook: fires on PreToolUse, injects ambient life context
so steward stays oriented mid-flight without polling.

Entry point: life hook tool (reads claude tool-call JSON from stdin).
"""

import json
import os
import sys
import time
from pathlib import Path

# Hook state file — throttle map persisted per session.
# Keyed by CLAUDE_SESSION_ID or PID fallback.
_STATE: dict[str, str] = {}
_STATE_PATH: Path | None = None


def _state_path() -> Path:
    key = os.environ.get("CLAUDE_SESSION_ID") or os.environ.get("STEWARD_SESSION_ID") or str(os.getppid())
    return Path(os.environ.get("TMPDIR", "/tmp")) / f".life_hook_{key}"


def _load_state() -> dict[str, str]:
    path = _state_path()
    if not path.exists():
        return {}
    fields: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            fields[k] = v
    return fields


def _save_state(state: dict[str, str]) -> None:
    path = _state_path()
    path.write_text("\n".join(f"{k}={v}" for k, v in state.items()) + "\n")


def _throttled(state: dict[str, str], key: str, interval: int) -> bool:
    last = state.get(key)
    if last is None:
        return False
    return (time.time() - float(last)) < interval


def _touch(state: dict[str, str], key: str) -> None:
    state[key] = str(time.time())


def _new_messages(state: dict[str, str], parts: list[str]) -> None:
    """Inject new telegram messages since last check."""
    if _throttled(state, "messages_at", 10):
        return
    _touch(state, "messages_at")

    from life.lib.store import get_db

    last_ts = state.get("messages_last_ts")
    if last_ts is None:
        state["messages_last_ts"] = str(time.time())
        return

    with get_db() as conn:
        rows = conn.execute(
            "SELECT direction, peer_name, body, timestamp FROM messages "
            "WHERE channel = 'telegram' AND timestamp > ? "
            "ORDER BY timestamp ASC LIMIT 10",
            (float(last_ts),),
        ).fetchall()

    if not rows:
        return

    # Update watermark to newest message
    state["messages_last_ts"] = str(max(r[3] for r in rows))

    lines = []
    for direction, peer_name, body, _ts in rows:
        arrow = "←" if direction == "in" else "→"
        name = peer_name or "?"
        text = (body or "")[:120]
        lines.append(f"  {arrow} {name}: {text}")

    parts.append("new messages:\n" + "\n".join(lines))


def _habit_status(state: dict[str, str], parts: list[str]) -> None:
    """Inject today's habit completion status."""
    if _throttled(state, "habits_at", 60):
        return
    _touch(state, "habits_at")

    from life.habit import get_habits
    from life.lib.clock import today

    habits = get_habits()
    if not habits:
        return

    today_date = today()
    done = []
    pending = []
    for h in habits:
        if h.cadence != "daily":
            continue
        checks_today = [c for c in h.checks if c.date() == today_date]
        if checks_today:
            done.append(h.content)
        else:
            pending.append(h.content)

    if not pending and not done:
        return

    line = f"habits: {len(done)}/{len(done) + len(pending)} done"
    if pending:
        line += f" — pending: {', '.join(pending[:5])}"
        if len(pending) > 5:
            line += f" +{len(pending) - 5} more"
    parts.append(line)


def _mood(state: dict[str, str], parts: list[str]) -> None:
    """Inject latest mood if recent."""
    if _throttled(state, "mood_at", 300):
        return
    _touch(state, "mood_at")

    from life.mood import get_recent_moods

    moods = get_recent_moods(hours=12)
    if not moods:
        return

    latest = moods[0]
    bar = "█" * latest.score + "░" * (5 - latest.score)
    label = f"  {latest.label}" if latest.label else ""
    parts.append(f"mood: {bar} {latest.score}/5{label}")


def _check_inbox(parts: list[str]) -> None:
    """Drain the inbox file — messages queued while steward was busy."""
    from life.daemon.inbound import pending_inbox

    content = pending_inbox()
    if content:
        parts.append(f"inbox (queued messages):\n{content}")


def _active_tasks(state: dict[str, str], parts: list[str]) -> None:
    """Inject open tasks."""
    if _throttled(state, "tasks_at", 60):
        return
    _touch(state, "tasks_at")

    from life.task import get_tasks

    tasks = get_tasks()
    if not tasks:
        return

    lines = [f"  · {t.content}" for t in tasks[:5]]
    header = f"tasks ({len(tasks)} open):"
    if len(tasks) > 5:
        lines.append(f"  +{len(tasks) - 5} more")
    parts.append(header + "\n" + "\n".join(lines))


def cmd_hook_tool() -> None:
    """PreToolUse hook — reads tool-call JSON from stdin, emits context."""
    from life.db import init

    init()

    sys.stdin.read()  # consume stdin (tool-call JSON) — ambient context only for now

    state = _load_state()
    parts: list[str] = []

    _check_inbox(parts)
    _new_messages(state, parts)
    _habit_status(state, parts)
    _mood(state, parts)
    _active_tasks(state, parts)

    _save_state(state)

    if parts:
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": "\n".join(parts),
            }
        }
        print(json.dumps(output), end="")


def main() -> None:
    """Entry point: life hook <event>"""
    args = sys.argv[1:]
    if not args:
        print("usage: life hook <tool>", file=sys.stderr)
        sys.exit(1)

    if args[0] == "tool":
        cmd_hook_tool()
    else:
        print(f"unknown hook event: {args[0]}", file=sys.stderr)
        sys.exit(1)

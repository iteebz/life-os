"""life hook — context injection for steward spawns.

Mirrors space hook: fires on PreToolUse, injects ambient life context
so steward stays oriented mid-flight without polling.

Entry point: life hook tool (reads claude tool-call JSON from stdin).
"""

import contextlib
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from life.comms import events
from life.core.config import get_user_name
from life.habit import get_habits
from life.lib.clock import today
from life.lib.store import get_db
from life.mood import get_recent_moods
from life.store.migrations import init
from life.task import get_tasks

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


def _render_inbox(rows) -> list[str]:
    return [f"  [{ch}] {name or '?'}: {(body or '')[:200]}" for _id, ch, name, body, _ts in rows]


def _inbox_signal(state: dict[str, str], parts: list[str]) -> None:
    rows = events.drain_inbox()
    if rows:
        parts.append("inbox:\n" + "\n".join(_render_inbox(rows)))


def _habit_status(state: dict[str, str], parts: list[str]) -> None:
    """Inject today's habit completion status."""
    if _throttled(state, "habits_at", 60):
        return
    _touch(state, "habits_at")

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

    moods = get_recent_moods(hours=12)
    if not moods:
        return

    latest = moods[0]
    bar = "█" * latest.score + "░" * (5 - latest.score)
    label = f"  {latest.label}" if latest.label else ""
    parts.append(f"mood: {bar} {latest.score}/5{label}")


def _active_tasks(state: dict[str, str], parts: list[str]) -> None:
    """Inject open tasks."""
    if _throttled(state, "tasks_at", 60):
        return
    _touch(state, "tasks_at")

    tasks = get_tasks()
    if not tasks:
        return

    lines = [f"  · {t.content}" for t in tasks[:5]]
    header = f"tasks ({len(tasks)} open):"
    if len(tasks) > 5:
        lines.append(f"  +{len(tasks) - 5} more")
    parts.append(header + "\n" + "\n".join(lines))


_LIFE_ROOT = Path.home() / "life"
_LIFE_OS_ROOT = _LIFE_ROOT / "life-os"


def _dirty_state(state: dict[str, str], parts: list[str]) -> None:
    """Once per spawn: surface uncommitted changes in ~/life."""
    if state.get("dirty_shown"):
        return
    state["dirty_shown"] = "1"
    with contextlib.suppress(Exception):
        result = subprocess.run(
            ["git", "-C", str(_LIFE_ROOT), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        if lines:
            summary = "\n".join(lines[:10])
            if len(lines) > 10:
                summary += f"\n... +{len(lines) - 10} more"
            parts.append(f"~/life dirty ({len(lines)} files):\n{summary}")


def _life_os_commits(state: dict[str, str], parts: list[str]) -> None:
    """Watermark-based: surface new life-os commits since last seen HEAD."""
    with contextlib.suppress(Exception):
        result = subprocess.run(
            ["git", "-C", str(_LIFE_OS_ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        head = result.stdout.strip()
        if not head:
            return
        last = state.get("life_os_head")
        state["life_os_head"] = head
        if last is None or last == head:
            return
        log = subprocess.run(
            ["git", "-C", str(_LIFE_OS_ROOT), "log", "--oneline", f"{last}..{head}"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        commits = log.stdout.strip()
        if commits:
            parts.append(f"life-os new commits:\n{commits[:400]}")


WRAP_THRESHOLD_CHARS = 100_000  # ~33k tokens
SLEEP_THRESHOLD_CHARS = 150_000  # ~50k tokens
WRAP_THRESHOLD_SECONDS = 3300  # 55m


def _log_turn(direction: str, body: str, session_id: str) -> None:
    if len(body) > 10000:
        body = body[:10000] + f"\n... [{len(body) - 10000} chars truncated]"
    ts = int(time.time())
    msg_id = f"chat-{session_id[:8]}-{ts}-{direction}"
    peer_name = get_user_name() if direction == "in" else "steward"
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
        )


def _ensure_session_row(claude_session_id: str) -> None:
    """Lazy-create session row on first human prompt. No conversation = no row."""
    if claude_session_id == "unknown" or os.environ.get("STEWARD_DB_SESSION_ID"):
        return
    name = os.environ.get("STEWARD_SESSION_NAME") or claude_session_id[:8]
    model = os.environ.get("STEWARD_SESSION_MODEL")
    source = os.environ.get("STEWARD_SESSION_SOURCE", "cli")
    with contextlib.suppress(Exception):
        with get_db() as conn:
            row = conn.execute(
                "SELECT id FROM sessions WHERE claude_session_id = ?",
                (claude_session_id,),
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
                "INSERT INTO sessions (summary, claude_session_id, name, model, source, "
                "state, started_at, last_active_at, pid) VALUES "
                "(?, ?, ?, ?, ?, 'active', "
                "STRFTIME('%Y-%m-%dT%H:%M:%S', 'now', 'localtime'), "
                "STRFTIME('%Y-%m-%dT%H:%M:%S', 'now', 'localtime'), ?)",
                (f"(active) {name}", claude_session_id, name, model, source, os.getppid()),
            )


def _surface_session_meta(session_id: str) -> None:
    with contextlib.suppress(Exception):
        with get_db() as conn:
            row = conn.execute(
                "SELECT id, logged_at FROM sessions WHERE claude_session_id = ?",
                (session_id,),
            ).fetchone()
            if not row:
                return
            db_id, logged_at = row
            char_row = conn.execute(
                "SELECT COALESCE(SUM(LENGTH(body)), 0) FROM messages WHERE channel = 'chat' AND peer = ?",
                (str(db_id),),
            ).fetchone()
            chars = char_row[0] if char_row else 0
        started = datetime.fromisoformat(logged_at).replace(tzinfo=UTC)
        age = int((datetime.now(UTC) - started).total_seconds())
        age_str = f"{age // 60}m" if age >= 60 else f"{age}s"
        nudge = ""
        if chars >= SLEEP_THRESHOLD_CHARS:
            nudge = '\nsleep now: close one loop, run `steward sleep "..."`, commit, end the session.'
        elif chars >= WRAP_THRESHOLD_CHARS:
            nudge = "\nwrap soon: prefer closing the open loop over starting new threads."
        elif age >= WRAP_THRESHOLD_SECONDS:
            nudge = "\nsession is long: consider closing soon."
        if nudge or chars > 50_000:
            print(f"\n<session-meta>session: {age_str} elapsed, {chars} chars logged{nudge}\n</session-meta>")


def _read_event() -> dict[str, Any]:
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return {}


def cmd_hook_prompt() -> None:
    """UserPromptSubmit — log human turn, surface inbox + session meta."""
    init()
    data = _read_event()
    body = (data.get("prompt") or "").strip()
    if not body:
        return
    session_id = os.environ.get("STEWARD_SESSION_ID", "unknown")
    _ensure_session_row(session_id)
    _log_turn("in", body, session_id)
    rows = events.drain_inbox()
    if rows:
        print("\n[new messages received while you were working]\n" + "\n".join(_render_inbox(rows)))
    _surface_session_meta(session_id)


def cmd_hook_stop() -> None:
    """Stop — log steward response."""
    init()
    data = _read_event()
    body = (data.get("response") or data.get("stopReason") or "").strip()
    if not body:
        return
    session_id = os.environ.get("STEWARD_SESSION_ID", "unknown")
    _log_turn("out", body, session_id)


def cmd_hook_tool() -> None:
    """PreToolUse hook — reads tool-call JSON from stdin, emits context."""
    init()

    sys.stdin.read()  # consume stdin (tool-call JSON) — ambient context only for now

    state = _load_state()
    parts: list[str] = []

    for fn in (_dirty_state, _life_os_commits, _inbox_signal, _habit_status, _mood, _active_tasks):
        try:
            fn(state, parts)
        except Exception as e:
            parts.append(f"[hook signal {fn.__name__} failed: {e}]")

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

    dispatch = {
        "tool": cmd_hook_tool,
        "prompt": cmd_hook_prompt,
        "stop": cmd_hook_stop,
    }
    fn = dispatch.get(args[0])
    if fn is None:
        print(f"unknown hook event: {args[0]}", file=sys.stderr)
        sys.exit(1)
    fn()

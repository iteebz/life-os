"""life hook — context injection for steward sessions.

Mirrors space hook: fires on PreToolUse, injects ambient life context
so steward stays oriented mid-flight without polling.

Entry point: life hook tool (reads claude tool-call JSON from stdin).
"""

import contextlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from life.comms import events
from life.habit import get_habits
from life.mood import get_recent_moods
from life.steward.sleep import _push_repos
from life.task import get_tasks
from lifeos.core.config import get_user_name
from lifeos.core.lib import frontmatter as fm
from lifeos.core.lib.clock import today
from lifeos.core.lib.store import get_db
from lifeos.core.store.migrations import init

# Hook state file — throttle map persisted per session.
# Keyed by STEWARD_SESSION_ID (falls back to PID).
_STATE: dict[str, str] = {}
_STATE_PATH: Path | None = None


def _state_path() -> Path:
    key = os.environ.get("STEWARD_SESSION_ID") or str(os.getppid())
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


def _ping_signal(state: dict[str, str], parts: list[str]) -> None:
    from life.steward.ping import drain

    last = int(state.get("last_ping_id", "0"))
    with contextlib.suppress(Exception):
        pings, max_id = drain(last)
        state["last_ping_id"] = str(max_id)
        for _, msg in pings:
            parts.append(f"[steward ping]: {msg}")


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
        is_vice = "vice" in (h.tags or [])
        checks_today = [c for c in h.checks if c.date() == today_date]
        if is_vice:
            # vice: checked = used (bad), unchecked = clean (good) — exclude from count
            continue
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


CTX_MAX_CHARS = 100_000
WRAP_THRESHOLD_SECONDS = 3300  # 55m


def _db_session_id(provider_session_id: str) -> int | None:
    """Resolve provider_session_id or numeric string to DB sessions.id."""
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


def _log_turn(direction: str, body: str, session_id: str) -> None:
    if len(body) > 10000:
        body = body[:10000] + f"\n... [{len(body) - 10000} chars truncated]"
    ts = int(time.time())
    msg_id = f"chat-{session_id[:8]}-{ts}-{direction}"
    peer_name = get_user_name() if direction == "in" else "steward"
    db_sid = _db_session_id(session_id)
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


def _ensure_session_row(provider_session_id: str) -> None:
    """Lazy-create session row on first human prompt. No conversation = no row.

    `provider_session_id` is the upstream provider's UUID (e.g. claude's session_id
    from the hook event payload). In cli mode the launcher sets STEWARD_SESSION_ID
    to that same UUID. In tg mode STEWARD_SESSION_ID is the numeric db id and we
    backfill the row's provider_session_id with the UUID from the event.
    """
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


def _surface_session_meta(session_id: str) -> None:
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
    provider_sid = data.get("session_id") or os.environ.get("STEWARD_SESSION_ID", "unknown")
    _ensure_session_row(provider_sid)
    _log_turn("in", body, provider_sid)
    rows = events.drain_inbox()
    if rows:
        print("\n[new messages received while you were working]\n" + "\n".join(_render_inbox(rows)))
    _surface_session_meta(provider_sid)


def cmd_hook_stop() -> None:
    """Stop — log steward response."""
    init()
    data = _read_event()
    body = (data.get("response") or data.get("stopReason") or "").strip()
    if not body:
        return
    provider_sid = data.get("session_id") or os.environ.get("STEWARD_SESSION_ID", "unknown")
    _log_turn("out", body, provider_sid)


def _auto_sleep_summary(session_id: str) -> str:
    """Generate a mechanical sleep summary from session message log."""
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
            topics = " / ".join(human_msgs[:3])
            parts.append(f"discussed: {topics}")
        if last_out:
            parts.append(f"last: {last_out}")
        return " — ".join(parts) if parts else "auto-closed"
    return "auto-closed (summary failed)"


def cmd_hook_post_tool() -> None:
    """PostToolUse — detect life done/habit completions, broadcast to inbox once per session."""
    init()
    data = _read_event()
    tool = data.get("tool_name", "")
    if tool != "Bash":
        return
    cmd = (data.get("tool_input") or {}).get("command", "")
    is_done = bool(re.search(r"\blife done\b", cmd))
    is_habit = bool(re.search(r"\blife habit\b.*\b(done|check)\b", cmd))
    if not is_done and not is_habit:
        return

    state = _load_state()
    session_id = os.environ.get("STEWARD_SESSION_ID", "unknown")
    flag = f"win_broadcast_{session_id[:8]}"
    if state.get(flag):
        return
    state[flag] = "1"
    _save_state(state)

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
    """SessionEnd — auto-sleep: close session record and push repos."""
    init()
    _read_event()  # consume stdin
    session_id = os.environ.get("STEWARD_SESSION_ID", "unknown")
    if session_id == "unknown":
        return

    summary = _auto_sleep_summary(session_id)

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
    """PreToolUse hook — reads tool-call JSON from stdin, emits context."""
    init()

    sys.stdin.read()  # consume stdin (tool-call JSON) — ambient context only for now

    session_id = os.environ.get("STEWARD_SESSION_ID", "unknown")
    with contextlib.suppress(Exception):
        _surface_session_meta(session_id)

    state = _load_state()
    parts: list[str] = []

    for fn in (_dirty_state, _life_os_commits, _inbox_signal, _ping_signal, _habit_status, _mood, _active_tasks):
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


_VALID_TYPES = {
    "feat",
    "fix",
    "refactor",
    "test",
    "docs",
    "style",
    "chore",
    "ops",
    "copy",
    "revert",
    "release",
    "perf",
    "sec",
    "memory",
    "brr",
    "ctx",
}


def _commit_fail(subject: str, reason: str) -> None:
    print(f"BLOCKED — {reason}\n  got: {subject}\n  format: type(scope): verb object", file=sys.stderr)
    sys.exit(1)


def cmd_hook_commit() -> None:
    """commit-msg — enforce conventional commit format and subject line rules."""
    args = [a for a in sys.argv[1:] if a not in ("hook", "commit")]
    if not args:
        print("usage: life hook commit <msg-file>", file=sys.stderr)
        sys.exit(1)
    msg_file = Path(args[0])
    if not msg_file.exists():
        sys.exit(0)
    subject = msg_file.read_text().splitlines()[0]

    # Allow merge/fixup commits
    if subject.startswith(("Merge ", "fixup!", "squash!")):
        sys.exit(0)

    # type(scope): subject or type: subject
    tag_pat = "|".join(_VALID_TYPES)
    if not re.match(rf"^({tag_pat})(\([a-z][a-z0-9_-]*\))?: .+", subject):
        _commit_fail(subject, "must be type(scope): verb object with a valid type")

    # No multi-scope
    if re.match(rf"^({tag_pat})\([^)]*,[^)]*\):", subject):
        _commit_fail(subject, "multiple scopes — split into one commit per scope")

    msg_body = subject.split(": ", 1)[1] if ": " in subject else subject

    if msg_body.endswith("."):
        _commit_fail(subject, "no trailing period")
    if "," in msg_body:
        _commit_fail(subject, "no commas — split into atomic commits")
    if "+" in msg_body:
        _commit_fail(subject, "no + — split into atomic commits")
    if " - " in subject:
        _commit_fail(subject, "' - ' is an em-dash proxy — rewrite without it")
    if ": " in msg_body:
        _commit_fail(subject, "no colon-space in message body")

    # Auto-sanitize em/en dashes
    em_dash = "\u2014"
    en_dash = "\u2013"
    if em_dash in subject or en_dash in subject:
        cleaned = subject.replace(em_dash, "-").replace(en_dash, "-")
        lines = msg_file.read_text().splitlines(keepends=True)
        lines[0] = cleaned + "\n"
        msg_file.write_text("".join(lines))
        subject = cleaned

    if len(subject) > 72:
        _commit_fail(subject, f"subject is {len(subject)} chars (max 72)")


# Frontmatter schemas — glob → (required_field, valid_values).
# None for valid_values means any non-empty value is fine.
_FRONTMATTER_SCHEMAS: dict[str, tuple[str, set[str] | None]] = {
    "notes/steward/trails/": ("description", None),
}


def _frontmatter_guard(root: Path, staged_all: list[str]) -> None:
    """Block commit when staged markdown breaks its frontmatter contract."""
    failures: list[str] = []
    for rel in staged_all:
        if not rel.endswith(".md"):
            continue
        schema = next(((g, s) for g, s in _FRONTMATTER_SCHEMAS.items() if rel.startswith(g)), None)
        if schema is None:
            continue
        _glob, (field, valid) = schema
        path = root / rel
        if not path.exists():
            continue
        value = fm.field(path.read_text(), field)
        if value is None:
            failures.append(f"  {rel}: missing '{field}:' in frontmatter")
        elif valid is not None and value not in valid:
            failures.append(f"  {rel}: {field}={value!r} not in {sorted(valid)}")
    if failures:
        print("BLOCKED — frontmatter guard:\n" + "\n".join(failures), file=sys.stderr)
        sys.exit(1)


def cmd_hook_pre_commit() -> None:
    """pre-commit — frontmatter guard + ruff format/lint on staged Python files."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        capture_output=True,
        text=True,
    )
    staged_all = result.stdout.splitlines()
    root = Path(subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip())
    _frontmatter_guard(root, staged_all)

    staged = [f for f in staged_all if f.endswith((".py", ".pyi"))]
    if not staged:
        return

    ruff = root / ".venv" / "bin" / "ruff"
    if not ruff.is_file():
        ruff = Path("ruff")

    fmt = subprocess.run([str(ruff), "format", "--check", *staged])
    if fmt.returncode != 0:
        print("BLOCKED — run 'ruff format' first", file=sys.stderr)
        sys.exit(1)

    lint = subprocess.run([str(ruff), "check", *staged])
    if lint.returncode != 0:
        print("BLOCKED — fix lint errors", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """Entry point: life hook <event>"""
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

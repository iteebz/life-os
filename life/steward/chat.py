"""steward — interactive sessions with tracking. Default command."""

import contextlib
import json
import os
import subprocess
import uuid
from datetime import datetime
from pathlib import Path

from fncli import cli

from life.ctx.assemble import build_chat_prompt
from life.lib import ansi
from life.lib.format import format_elapsed
from life.lib.providers.claude import build_env

from . import add_session, add_spawn, close_spawn, get_sessions, set_spawn_pid, update_session_followups, update_session_summary, update_spawn_provider_session

LIFE_DIR = Path.home() / "life"
TOOLS = "Bash,Read,Write,Edit,Grep,Glob,WebFetch,WebSearch"
DEFAULT_MODEL = "sonnet"
SESSION_TIMEOUT = 3300  # 55m
SESSION_MAX_CHARS = 100_000

# in-process state; rebuilt from DB on resume across process boundaries
_session_start: datetime | None = None
_followups: list[datetime] = []
_db_session_id: int | None = None


def _load_session_state(db_id: int) -> None:
    """Reconstruct timeline from DB for resume across process boundaries."""
    global _session_start, _followups, _db_session_id
    sessions = get_sessions(limit=50)
    match = next((s for s in sessions if s.id == db_id), None)
    if match:
        _session_start = match.logged_at
        _followups = [datetime.fromisoformat(ts) for ts in (match.follow_ups or [])]
    _db_session_id = db_id


def _session_meta_fragment(source: str) -> str:
    now = datetime.now()
    start = _session_start or now
    elapsed_s = int((now - start).total_seconds())
    elapsed_str = f"{elapsed_s // 60}m{elapsed_s % 60}s" if elapsed_s >= 60 else f"{elapsed_s}s"
    timeline = ", ".join(
        f"+{int((t - start).total_seconds())}s" for t in _followups
    ) if _followups else "none"
    return (
        f"\n\n[session meta] source={source} | started={start.strftime('%H:%M:%S')} | "
        f"runtime={elapsed_str} | follow-ups={timeline} | ts={now.isoformat(timespec='seconds')}"
    )


def _ensure_hooks_config() -> None:
    """Write hooks into ~/life/.claude/settings.local.json so chat turns get logged."""
    settings_path = LIFE_DIR / ".claude" / "settings.local.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[str, object] = {}
    if settings_path.exists():
        with contextlib.suppress(json.JSONDecodeError, ValueError):
            existing = json.loads(settings_path.read_text())

    project = str(LIFE_DIR / "life-os")
    runner = f"uv run --project {project} life-hook"
    desired_hooks = {
        "UserPromptSubmit": [
            {"matcher": "", "hooks": [{"type": "command", "command": f"{runner} prompt"}]}
        ],
        "Stop": [
            {"matcher": "", "hooks": [{"type": "command", "command": f"{runner} stop"}]}
        ],
    }

    if existing.get("hooks") != desired_hooks:
        existing["hooks"] = desired_hooks
        settings_path.write_text(json.dumps(existing, indent=2) + "\n")


def _build_system_prompt(source: str, raw: bool) -> str:
    """Compose --append-system-prompt: wake context (unless raw) + session meta."""
    parts = []
    if not raw:
        wake = build_chat_prompt()
        if wake:
            parts.append(wake)
    parts.append(_session_meta_fragment(source))
    return "\n\n".join(parts)


def _unlock_keychain() -> None:
    if os.environ.get("KEYCHAIN_UNLOCKED"):
        return
    home = Path.home()
    keychain = home / "Library" / "Keychains" / "login.keychain-db"
    if keychain.exists():
        subprocess.run(["security", "unlock-keychain", str(keychain)])
        os.environ["KEYCHAIN_UNLOCKED"] = "true"


def _launch(
    model: str,
    session_id: str,
    name: str | None = None,
    resume: bool = False,
    source: str = "cli",
    db_session_id: int | None = None,
    raw: bool = False,
) -> int:
    global _session_start, _db_session_id

    if resume and db_session_id is not None:
        _load_session_state(db_session_id)
        _followups.append(datetime.now())
        update_session_followups(db_session_id, [ts.isoformat() for ts in _followups])
    else:
        if _session_start is None:
            _session_start = datetime.now()
        else:
            _followups.append(datetime.now())
            if db_session_id is not None:
                update_session_followups(db_session_id, [ts.isoformat() for ts in _followups])

    spawn_id = add_spawn(mode="chat", source=source, session_id=db_session_id)
    _ensure_hooks_config()

    cmd = [
        "claude",
        "--model", model,
        "--dangerously-skip-permissions",
        "--tools", TOOLS,
        "--append-system-prompt", _build_system_prompt(source, raw or resume),
        "--name", "steward",
    ]
    if resume:
        cmd.extend(["--resume", session_id])
    else:
        cmd.extend(["--session-id", session_id])

    _unlock_keychain()
    env = build_env("chat")
    env["STEWARD_SESSION_ID"] = session_id
    env["STEWARD_SPAWN_ID"] = str(spawn_id)
    env["GIT_AUTHOR_NAME"] = "steward"
    env["GIT_AUTHOR_EMAIL"] = "steward@life.local"
    env["GIT_COMMITTER_NAME"] = "steward"
    env["GIT_COMMITTER_EMAIL"] = "steward@life.local"

    proc = subprocess.Popen(cmd, cwd=LIFE_DIR, env=env)
    set_spawn_pid(spawn_id, proc.pid)
    update_spawn_provider_session(spawn_id, session_id)
    rc = proc.wait()
    close_spawn(spawn_id, status="complete" if rc == 0 else "error")
    return rc


@cli("steward", flags={"model": ["-m", "--model"], "name": ["-n", "--name"], "opus": ["--opus"], "raw": ["--raw"]})
def chat(model: str | None = None, name: str | None = None, opus: bool = False, raw: bool = False):
    """Start a tracked interactive steward session"""
    if opus:
        model = "opus"
    model = model or DEFAULT_MODEL
    session_id = str(uuid.uuid4())
    label = name or datetime.now().strftime("%b %d %H:%M").lower()

    source = os.environ.get("STEWARD_SOURCE", "cli")
    db_id = add_session(
        summary=f"(active) {label}",
        claude_session_id=session_id,
        name=label,
        model=model,
        source=source,
    )


    print(f"session {db_id} → {session_id[:8]}  model={model}  source={source}{'  raw' if raw else ''}")
    rc = _launch(model, session_id, name=label, source=source, db_session_id=db_id, raw=raw)
    update_session_summary(db_id, f"(closed) {label}")
    return rc


@cli("steward", flags={"ref": [], "model": ["-m", "--model"]})
def resume(ref: str | None = None, model: str | None = None):
    """Resume a previous session, or list resumable sessions"""
    sessions = get_sessions(limit=20)
    resumable = [s for s in sessions if s.claude_session_id]

    if not resumable:
        print("no resumable sessions")
        return 1

    if ref is None:
        now = datetime.now()
        for s in resumable[:10]:
            rel = format_elapsed(s.logged_at, now)
            model_str = f"  {s.model}" if s.model else ""
            name_str = s.name or ""
            sid = s.claude_session_id[:8] if s.claude_session_id else ""
            print(f"  {ansi.muted(str(s.id)):>4}  {sid}  {rel:<10}  {name_str}{model_str}")
        return 0

    # resolve by DB id or session UUID prefix
    target = None
    for s in resumable:
        if str(s.id) == ref:
            target = s
            break
        if s.claude_session_id and s.claude_session_id.startswith(ref):
            target = s
            break

    if not target or not target.claude_session_id:
        print(f"no session matching '{ref}'")
        return 1

    m = model or target.model or DEFAULT_MODEL
    source = os.environ.get("STEWARD_SOURCE", "cli")
    print(f"resuming {target.id} → {target.claude_session_id[:8]}  model={m}  source={source}")
    return _launch(m, target.claude_session_id, name=target.name, resume=True, source=source, db_session_id=target.id)


@cli("steward", name="continue", aliases=["c"])
def continue_session():
    """Continue the most recent steward session"""
    sessions = get_sessions(limit=5)
    resumable = [s for s in sessions if s.claude_session_id]

    if not resumable:
        print("no sessions to continue")
        return 1

    target = resumable[0]
    m = target.model or DEFAULT_MODEL
    source = os.environ.get("STEWARD_SOURCE", "cli")
    if not target.claude_session_id:
        raise ValueError(f"session {target.id} has no claude_session_id")
    print(f"continuing {target.id} → {target.claude_session_id[:8]}  model={m}  source={source}")
    return _launch(m, target.claude_session_id, name=target.name, resume=True, source=source, db_session_id=target.id)

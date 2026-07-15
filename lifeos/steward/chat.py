"""steward — interactive sessions with tracking. Default command."""

import json
import os
import subprocess
import uuid
from datetime import datetime
from pathlib import Path

from fncli import cli

from lifeos.core.ctx.assemble import build_chat_prompt
from lifeos.core.lib.providers.claude import build_env
from lifeos.core.lib.store import get_db

from . import (
    get_sessions,
    set_session_active,
    set_session_idle,
    set_session_pid,
    update_session_followups,
)

LIFE_DIR = Path.home() / "life"
TOOLS = "Bash,Read,Write,Edit,Grep,Glob,WebFetch,WebSearch"
DEFAULT_MODEL = "claude-sonnet-5"
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
        _session_start = match.started_at or match.logged_at
        _followups = [datetime.fromisoformat(ts) for ts in (match.follow_ups or [])]
    _db_session_id = db_id


def _session_meta_fragment(source: str) -> str:
    now = datetime.now()
    start = _session_start or now
    elapsed_s = int((now - start).total_seconds())
    elapsed_str = f"{elapsed_s // 60}m{elapsed_s % 60}s" if elapsed_s >= 60 else f"{elapsed_s}s"
    timeline = ", ".join(f"+{int((t - start).total_seconds())}s" for t in _followups) if _followups else "none"
    return (
        f"\n\n[session meta] source={source} | started={start.strftime('%H:%M:%S')} | "
        f"runtime={elapsed_str} | follow-ups={timeline} | ts={now.isoformat(timespec='seconds')}"
    )


def _build_hook_settings_json() -> str:
    """Return --settings JSON with all steward hooks. Injected at spawn time — no filesystem writes."""
    runner = f"uv run --project {LIFE_DIR / 'life-os'} steward hook"
    return json.dumps(
        {
            "statusLine": {
                "type": "command",
                "command": str(Path.home() / ".local/bin/life-statusline"),
                "padding": 0,
            },
            "hooks": {
                "PreToolUse": [{"matcher": "", "hooks": [{"type": "command", "command": f"{runner} tool"}]}],
                "PostToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": f"{runner} post-tool"}]}],
                "UserPromptSubmit": [{"matcher": "", "hooks": [{"type": "command", "command": f"{runner} prompt"}]}],
                "Stop": [{"matcher": "", "hooks": [{"type": "command", "command": f"{runner} stop"}]}],
                "SessionEnd": [{"matcher": "", "hooks": [{"type": "command", "command": f"{runner} session-end"}]}],
            },
        }
    )


def _build_system_prompt(source: str, raw: bool) -> str:
    """Compose --append-system-prompt: wake context (unless raw) + session meta."""
    parts = []
    if not raw:
        wake = build_chat_prompt()
        if wake:
            parts.append(wake)
    parts.append(_session_meta_fragment(source))
    return "\n\n".join(parts)


_API_KEY_FILE = Path.home() / ".life" / "api_key"


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
        set_session_active(db_session_id)
    else:
        if _session_start is None:
            _session_start = datetime.now()
        else:
            _followups.append(datetime.now())
            if db_session_id is not None:
                update_session_followups(db_session_id, [ts.isoformat() for ts in _followups])
            else:
                _persist_followup(session_id, _followups)

    cmd = [
        "claude",
        "--model",
        model,
        "--dangerously-skip-permissions",
        "--tools",
        TOOLS,
        "--append-system-prompt",
        _build_system_prompt(source, raw or resume),
        "--name",
        f"steward ({_display_model(model)})",
        "--settings",
        _build_hook_settings_json(),
    ]
    if resume:
        cmd.extend(["--resume", session_id])
    else:
        cmd.extend(["--session-id", session_id])

    env = build_env("chat")
    env["STEWARD_SESSION_ID"] = session_id
    if db_session_id is not None:
        env["STEWARD_DB_SESSION_ID"] = str(db_session_id)
    env["STEWARD_SESSION_NAME"] = name or session_id[:8]
    env["STEWARD_SESSION_MODEL"] = model
    env["STEWARD_SESSION_SOURCE"] = source
    env["GIT_AUTHOR_NAME"] = "steward"
    env["GIT_AUTHOR_EMAIL"] = "steward@life-os"
    env["GIT_COMMITTER_NAME"] = "steward"
    env["GIT_COMMITTER_EMAIL"] = "steward@life-os"

    print(f"\033]0;steward ({_display_model(model)})\007", end="", flush=True)
    proc = subprocess.Popen(cmd, cwd=LIFE_DIR, env=env)
    if db_session_id is not None:
        set_session_pid(db_session_id, proc.pid)
    rc = proc.wait()
    resolved_id = db_session_id or _lookup_session_id(session_id)
    if resolved_id is not None:
        set_session_idle(resolved_id)
    return rc


_MODEL_LABELS = {
    "opus": "opus-4.6",
    "sonnet": "sonnet-5",
    "claude-sonnet-5": "sonnet-5",
    "claude-fable-5": "fable-5",
}


def _display_model(model: str) -> str:
    return _MODEL_LABELS.get(model, model)


def _lookup_session_id(provider_session_id: str) -> int | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM sessions WHERE provider_session_id = ? ORDER BY id DESC LIMIT 1",
            (provider_session_id,),
        ).fetchone()
    return row[0] if row else None


def _persist_followup(provider_session_id: str, followups: list[datetime]) -> None:
    db_id = _lookup_session_id(provider_session_id)
    if db_id is not None:
        update_session_followups(db_id, [ts.isoformat() for ts in followups])


@cli("life steward", flags={"key": []})
def set_key(key: str):
    """Store API key in ~/.life/api_key (no keychain, works over SSH)"""
    _API_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    _API_KEY_FILE.write_text(key.strip() + "\n")
    _API_KEY_FILE.chmod(0o600)
    print(f"key stored → {_API_KEY_FILE}")


@cli(
    "life steward",
    flags={
        "model": ["-m", "--model"],
        "name": ["-n", "--name"],
        "opus": ["--opus"],
        "sonnet": ["--sonnet"],
        "fable": ["--fable"],
        "raw": ["--raw"],
    },
)
def chat(
    model: str | None = None,
    name: str | None = None,
    opus: bool = False,
    sonnet: bool = False,
    fable: bool = False,
    raw: bool = False,
):
    """Start a tracked interactive steward session"""
    if opus:
        model = "opus"
    elif sonnet:
        model = "claude-sonnet-5"
    elif fable:
        model = "claude-fable-5"
    model = model or DEFAULT_MODEL
    session_id = str(uuid.uuid4())
    label = name or datetime.now().strftime("%b %d %H:%M").lower()

    source = os.environ.get("STEWARD_SOURCE", "cli")
    print(f"session → {session_id[:8]}  model={model}  source={source}{'  raw' if raw else ''}")
    return _launch(model, session_id, name=label, source=source, db_session_id=None, raw=raw)


@cli("life steward", flags={"ref": [], "model": ["-m", "--model"]})
def resume(ref: str, model: str | None = None):
    """Resume a session by DB id or session UUID prefix"""
    sessions = get_sessions(limit=20)
    resumable = [s for s in sessions if s.provider_session_id]

    target = None
    for s in resumable:
        if str(s.id) == ref:
            target = s
            break
        if s.provider_session_id and s.provider_session_id.startswith(ref):
            target = s
            break

    if not target or not target.provider_session_id:
        print(f"no session matching '{ref}'")
        return 1

    m = model or target.model or DEFAULT_MODEL
    source = os.environ.get("STEWARD_SOURCE", "cli")
    print(f"resuming {target.id} → {target.provider_session_id[:8]}  model={m}  source={source}")
    return _launch(m, target.provider_session_id, name=target.name, resume=True, source=source, db_session_id=target.id)

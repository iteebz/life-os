"""steward — interactive sessions with tracking. Default command."""

import subprocess
import uuid
from datetime import datetime
from pathlib import Path

from fncli import cli

from life.lib import ansi
from life.lib.format import format_elapsed

from . import add_session, get_sessions, update_session_summary

LIFE_DIR = Path.home() / "life"
TOOLS = "Bash,Read,Write,Edit,Grep,Glob,WebFetch,WebSearch"
DEFAULT_MODEL = "sonnet"


def _launch(model: str, session_id: str, name: str | None = None, resume: bool = False) -> int:
    cmd = [
        "claude",
        "--model", model,
        "--dangerously-skip-permissions",
        "--tools", TOOLS,
    ]
    if resume:
        cmd.extend(["--resume", session_id])
    else:
        cmd.extend(["--session-id", session_id])
    if name:
        cmd.extend(["--name", name])

    from life.lib.providers.claude import build_env

    env = build_env("chat")
    env["STEWARD_SESSION_ID"] = session_id
    env["GIT_AUTHOR_NAME"] = "steward"
    env["GIT_AUTHOR_EMAIL"] = "steward@life.local"
    env["GIT_COMMITTER_NAME"] = "steward"
    env["GIT_COMMITTER_EMAIL"] = "steward@life.local"

    return subprocess.call(cmd, cwd=LIFE_DIR, env=env)


@cli("steward", default=True, flags={"model": ["-m", "--model"], "name": ["-n", "--name"], "opus": ["--opus"]})
def chat(model: str | None = None, name: str | None = None, opus: bool = False):
    """Start a tracked interactive steward session"""
    if opus:
        model = "opus"
    model = model or DEFAULT_MODEL
    session_id = str(uuid.uuid4())
    label = name or datetime.now().strftime("%b %d %H:%M").lower()

    db_id = add_session(
        summary=f"(active) {label}",
        claude_session_id=session_id,
        name=label,
        model=model,
    )

    print(f"session {db_id} → {session_id[:8]}  model={model}")
    rc = _launch(model, session_id, name=label)
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
    print(f"resuming {target.id} → {target.claude_session_id[:8]}  model={m}")
    return _launch(m, target.claude_session_id, name=target.name, resume=True)


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
    assert target.claude_session_id
    print(f"continuing {target.id} → {target.claude_session_id[:8]}  model={m}")
    return _launch(m, target.claude_session_id, name=target.name, resume=True)

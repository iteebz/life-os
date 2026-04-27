"""steward — interactive sessions with tracking. Default command."""

import os
import subprocess
import uuid
from datetime import datetime
from pathlib import Path

from fncli import cli

from life.lib import ansi
from life.lib.format import format_elapsed

from . import add_session, add_spawn, close_spawn, get_sessions, update_session_followups, update_session_summary

LIFE_DIR = Path.home() / "life"
TOOLS = "Bash,Read,Write,Edit,Grep,Glob,WebFetch,WebSearch"
DEFAULT_MODEL = "sonnet"

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


def _launch(
    model: str,
    session_id: str,
    name: str | None = None,
    resume: bool = False,
    source: str = "cli",
    db_session_id: int | None = None,
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

    cmd = [
        "claude",
        "--model", model,
        "--dangerously-skip-permissions",
        "--tools", TOOLS,
        "--append-system-prompt", _session_meta_fragment(source),
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
    env["STEWARD_SPAWN_ID"] = str(spawn_id)
    env["GIT_AUTHOR_NAME"] = "steward"
    env["GIT_AUTHOR_EMAIL"] = "steward@life.local"
    env["GIT_COMMITTER_NAME"] = "steward"
    env["GIT_COMMITTER_EMAIL"] = "steward@life.local"

    rc = subprocess.call(cmd, cwd=LIFE_DIR, env=env)
    close_spawn(spawn_id, status="complete" if rc == 0 else "error")
    return rc


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

    source = os.environ.get("STEWARD_SOURCE", "cli")
    print(f"session {db_id} → {session_id[:8]}  model={model}  source={source}")
    rc = _launch(model, session_id, name=label, source=source, db_session_id=db_id)
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

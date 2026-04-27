"""Session reaper — close idle sessions past warm window.

50m: wake interactive session to self-sleep with summary.
55m: hard close if it didn't self-sleep.
"""

import os
import shutil
import signal
import subprocess
from datetime import datetime
from pathlib import Path

from life.daemon.shared import IDLE_REAP_SECS, IDLE_WAKE_SECS, log
from life.steward import Session, close_session, get_sessions

WAKE_MARKER_DIR = Path.home() / ".life"
LIFE_DIR = Path.home() / "life"


def _idle_seconds(session: Session) -> float | None:
    ts = session.last_active_at or session.started_at
    if not ts:
        return None
    try:
        return (datetime.now() - ts).total_seconds()
    except Exception:
        return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _wake_marker(session_id: int) -> Path:
    return WAKE_MARKER_DIR / f".session-{session_id}-waked"


def _wake_to_sleep(session: Session) -> None:
    marker = _wake_marker(session.id)
    if marker.exists():
        return
    if not session.claude_session_id:
        return
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("")

    claude = shutil.which("claude")
    if not claude:
        log(f"[reap] wake_to_sleep: claude not found for session {session.id}")
        return

    prompt = (
        "your session has been idle and the prompt cache is about to expire. "
        "call `life sleep` now with a summary of what happened this session."
    )
    try:
        subprocess.Popen(
            [claude, "-p", "--resume", session.claude_session_id, "--dangerously-skip-permissions", "--bare", prompt],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=LIFE_DIR,
        )
        log(f"[reap] wake_to_sleep: spawned for session {session.id}")
    except Exception as e:
        log(f"[reap] wake_to_sleep: failed for session {session.id}: {e}")


def _hard_reap(session: Session) -> None:
    log(f"[reap] hard reap: session {session.id} (pid {session.pid})")
    if session.pid and _pid_alive(session.pid):
        try:
            os.kill(session.pid, signal.SIGTERM)
        except OSError:
            pass
    close_session(session.id)
    _wake_marker(session.id).unlink(missing_ok=True)


def sweep() -> None:
    sessions = get_sessions(limit=50, state="active") + get_sessions(limit=50, state="idle")
    for session in sessions:
        # Clean up sessions with dead pids
        if session.pid and not _pid_alive(session.pid) and session.state == "active":
            from life.steward import set_session_idle
            set_session_idle(session.id)
            continue

        idle = _idle_seconds(session)
        if idle is None:
            continue

        if idle > IDLE_REAP_SECS:
            _hard_reap(session)
        elif idle > IDLE_WAKE_SECS and session.pid and _pid_alive(session.pid):
            log(f"[reap] idle wake: session {session.id} (idle {int(idle)}s)")
            _wake_to_sleep(session)

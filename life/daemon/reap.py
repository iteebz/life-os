"""Idle session reap — 50/55/60 cache TTL lifecycle.

50m: wake agent headlessly to self-sleep with a real summary.
55m: hard reap if agent didn't self-sleep.
60m: cache TTL expires naturally.
"""

import os
import shutil
import signal
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from life.daemon.shared import IDLE_REAP_SECS, IDLE_WAKE_SECS, log
from life.lib.store import get_db

WAKE_MARKER_DIR = Path.home() / ".life"
LIFE_DIR = Path.home() / "life"


def _active_chat_spawns() -> list[dict[str, Any]]:
    try:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT id, pid, last_active_at, provider_session_id, started_at "
                "FROM spawns WHERE status = 'active' AND mode = 'chat' AND pid IS NOT NULL"
            ).fetchall()
        return [
            {
                "id": row[0],
                "pid": row[1],
                "last_active_at": row[2],
                "provider_session_id": row[3],
                "started_at": row[4],
            }
            for row in rows
        ]
    except Exception:
        return []


def _idle_seconds(spawn: dict[str, Any]) -> float | None:
    ts_str = spawn.get("last_active_at") or spawn.get("started_at")
    if not ts_str:
        return None
    try:
        ts = datetime.fromisoformat(ts_str)
        return (datetime.now() - ts).total_seconds()
    except Exception:
        return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _wake_marker(spawn_id: int) -> Path:
    return WAKE_MARKER_DIR / f".spawn-{spawn_id}-waked"


def _wake_to_sleep(provider_session_id: str, spawn_id: int) -> None:
    marker = _wake_marker(spawn_id)
    if marker.exists():
        return
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("")

    claude = shutil.which("claude")
    if not claude:
        log(f"[reap] wake_to_sleep: claude not found for spawn {spawn_id}")
        return

    prompt = (
        "your session has been idle and the prompt cache is about to expire. "
        "call `space sleep` now with a summary of what happened this session."
    )
    try:
        subprocess.Popen(
            [claude, "-p", "--resume", provider_session_id, "--dangerously-skip-permissions", "--bare", prompt],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=LIFE_DIR,
        )
        log(f"[reap] wake_to_sleep: spawned for {spawn_id}")
    except Exception as e:
        log(f"[reap] wake_to_sleep: failed for {spawn_id}: {e}")


def _hard_reap(spawn_id: int, pid: int) -> None:
    from life.steward import close_spawn

    log(f"[reap] hard reap: spawn {spawn_id} (pid {pid})")
    # Mark as slept in DB
    try:
        with get_db() as conn:
            conn.execute(
                "UPDATE spawns SET slept_at = STRFTIME('%Y-%m-%dT%H:%M:%S', 'now') WHERE id = ?",
                (spawn_id,),
            )
    except Exception:
        pass
    # SIGTERM the claude process
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass
    close_spawn(spawn_id, status="complete")
    # Clean up wake marker
    _wake_marker(spawn_id).unlink(missing_ok=True)


def sweep() -> None:
    for spawn in _active_chat_spawns():
        pid = spawn["pid"]
        if not _pid_alive(pid):
            continue

        idle = _idle_seconds(spawn)
        if idle is None:
            continue

        spawn_id = spawn["id"]
        if idle > IDLE_REAP_SECS:
            _hard_reap(spawn_id, pid)
        elif idle > IDLE_WAKE_SECS:
            provider_sid = spawn.get("provider_session_id")
            if provider_sid:
                log(f"[reap] idle wake: spawn {spawn_id} (idle {int(idle)}s)")
                _wake_to_sleep(provider_sid, spawn_id)

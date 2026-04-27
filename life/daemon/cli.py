import contextlib
import os
import shutil
import signal as _signal
import subprocess
import threading
import time
from pathlib import Path

from fncli import cli

from life.daemon.__main__ import supervise
from life.daemon.session import get_tyson_chat_id, run_session
from life.daemon.shared import pid
from life.daemon.spawn import fetch_wake_context

_LABEL = "com.life.daemon"
_PLIST_SRC = Path(__file__).parent.parent.parent / "scripts" / f"{_LABEL}.plist"
_PLIST_DST = Path.home() / "Library" / "LaunchAgents" / f"{_LABEL}.plist"


def _launchd_loaded() -> bool:
    result = subprocess.run(["launchctl", "list", _LABEL], capture_output=True)
    return result.returncode == 0


def _launchd_start() -> None:
    _PLIST_DST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_PLIST_SRC, _PLIST_DST)
    subprocess.run(["launchctl", "load", str(_PLIST_DST)], capture_output=True)


def _launchd_stop() -> None:
    subprocess.run(["launchctl", "unload", str(_PLIST_DST)], capture_output=True)
    _PLIST_DST.unlink(missing_ok=True)


def _kill_supervisor(p: int) -> None:
    with contextlib.suppress(ProcessLookupError):
        os.killpg(p, _signal.SIGTERM)
    for _ in range(50):
        time.sleep(0.1)
        if pid() is None:
            return
    with contextlib.suppress(ProcessLookupError):
        os.killpg(p, _signal.SIGKILL)


@cli("life daemon", name="run")
def daemon_run() -> None:
    """supervisor entry point — called by launchd, do not invoke directly"""
    supervise()


@cli("life daemon", name="start")
def daemon_start() -> None:
    """start daemon"""
    existing = pid()
    if existing:
        print(f"already running (pid {existing})")
        return
    _launchd_start()
    for _ in range(30):
        time.sleep(0.1)
        if p := pid():
            print(f"started (pid {p})")
            return
    print("started (pid unknown)")


@cli("life daemon", name="stop")
def daemon_stop() -> None:
    """stop daemon"""
    p = pid()
    if p is None and not _launchd_loaded():
        print("not running")
        return
    if p:
        _kill_supervisor(p)
    _launchd_stop()
    print("stopped")


@cli("life daemon", name="status")
def daemon_status() -> None:
    """show daemon status"""
    p = pid()
    loaded = _launchd_loaded()
    launchd_str = "loaded" if loaded else "not loaded"
    if p:
        print(f"running (pid {p}) | launchd: {launchd_str}")
    else:
        print(f"stopped | launchd: {launchd_str}")


@cli("life daemon", name="restart")
def daemon_restart() -> None:
    """restart daemon"""
    if p := pid():
        _kill_supervisor(p)
    _launchd_stop()
    _launchd_start()
    for _ in range(30):
        time.sleep(0.1)
        if new_p := pid():
            print(f"restarted (pid {new_p})")
            return
    print("restarted (pid unknown)")


@cli("life daemon", name="nightly")
def daemon_nightly() -> None:
    """trigger a nightly steward session now (for testing)"""
    if pid():
        print("daemon is running — stop it first or let the nightly thread handle it")
        return

    chat_id = get_tyson_chat_id()
    if not chat_id:
        print("no telegram chat_id for tyson")
        return

    stop = threading.Event()
    claimed = threading.Event()
    print(f"triggering nightly session (chat_id={chat_id})")

    wake = fetch_wake_context()
    opener = (
        f"Current life state:\n{wake}\n\n"
        "<brief>\n"
        "Objective: evening brief via Telegram. It's 8pm.\n"
        "Good evening brief: what moved today, what's still open, one thing to close if he has energy. "
        "Honest, not cheerful. Start with 🌱. Plain text only. 2-3 sentences.\n"
        "</brief>"
    )

    try:
        run_session(chat_id, opener, stop, claimed, label="nightly")
    except KeyboardInterrupt:
        stop.set()
        claimed.clear()
        print("\nsession interrupted")

import contextlib
import os
import shutil
import signal as _signal
import subprocess
import time
from pathlib import Path

from fncli import cli

_LABEL = "com.life.daemon"
_PLIST_SRC = Path(__file__).parent.parent.parent / "scripts" / f"{_LABEL}.plist"
_PLIST_DST = Path.home() / "Library" / "LaunchAgents" / f"{_LABEL}.plist"
_LOCK_FILE = Path.home() / ".life" / "daemon.lock"


def _pid() -> int | None:
    if not _LOCK_FILE.exists():
        return None
    try:
        raw = _LOCK_FILE.read_text().strip()
        if not raw.isdigit():
            return None
        p = int(raw)
        os.kill(p, 0)
        return p
    except (OSError, ValueError):
        return None


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
        if _pid() is None:
            return
    with contextlib.suppress(ProcessLookupError):
        os.killpg(p, _signal.SIGKILL)


@cli("life daemon", name="run")
def daemon_run() -> None:
    """supervisor entry point — called by launchd, do not invoke directly"""
    from life.daemon.__main__ import supervise

    supervise()


@cli("life daemon", name="start")
def daemon_start() -> None:
    """start daemon"""
    existing = _pid()
    if existing:
        print(f"already running (pid {existing})")
        return
    _launchd_start()
    for _ in range(30):
        time.sleep(0.1)
        if p := _pid():
            print(f"started (pid {p})")
            return
    print("started (pid unknown)")


@cli("life daemon", name="stop")
def daemon_stop() -> None:
    """stop daemon"""
    p = _pid()
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
    p = _pid()
    loaded = _launchd_loaded()
    launchd_str = "loaded" if loaded else "not loaded"
    if p:
        print(f"running (pid {p}) | launchd: {launchd_str}")
    else:
        print(f"stopped | launchd: {launchd_str}")


@cli("life daemon", name="restart")
def daemon_restart() -> None:
    """restart daemon"""
    if p := _pid():
        _kill_supervisor(p)
    _launchd_stop()
    _launchd_start()
    for _ in range(30):
        time.sleep(0.1)
        if new_p := _pid():
            print(f"restarted (pid {new_p})")
            return
    print("restarted (pid unknown)")

"""Supervisor: owns the lock file, restarts child on crash.

Imports ZERO life.* modules — immune to bad edits in the codebase.
"""

import contextlib
import fcntl
import os
import signal
import subprocess
import sys
import time
from io import TextIOWrapper
from pathlib import Path

BACKOFF_BASE = 2
BACKOFF_CAP = 120
HEALTHY_THRESHOLD = 10


def _dot_life() -> Path:
    return Path(os.environ.get("LIFE_DOT_LIFE", Path.home() / ".life"))


def _lock_path() -> Path:
    return _dot_life() / "daemon.lock"


def _log_path() -> Path:
    return _dot_life() / "daemon.log"


def _acquire_lock() -> TextIOWrapper | None:
    lock_file = _lock_path()
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    fd = lock_file.open("w")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fd.close()
        return None
    fd.write(str(os.getpid()))
    fd.flush()
    return fd


def _spawn_child(log_fd) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [sys.executable, "-c", "from life.daemon.run import run; run()"],
        stdout=subprocess.DEVNULL,
        stderr=log_fd,
        start_new_session=True,
    )


def supervise() -> None:
    with contextlib.suppress(PermissionError):
        os.setpgid(0, 0)

    lock_fd = _acquire_lock()
    if lock_fd is None:
        return

    log_fd = _log_path().open("a")
    failures = 0
    child = _spawn_child(log_fd)

    def _forward_term(_sig, _frame):
        try:
            child.send_signal(signal.SIGTERM)
            child.wait(timeout=5)
        except (subprocess.TimeoutExpired, OSError):
            child.kill()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _forward_term)
    signal.signal(signal.SIGINT, _forward_term)

    start_time = time.monotonic()

    try:
        while True:
            status = child.poll()

            if status is not None:
                uptime = time.monotonic() - start_time
                if uptime > HEALTHY_THRESHOLD:
                    failures = 0
                else:
                    failures += 1

                delay = min(BACKOFF_BASE * (2**failures), BACKOFF_CAP)
                time.sleep(delay)

                child = _spawn_child(log_fd)
                start_time = time.monotonic()
                continue

            time.sleep(2)
    finally:
        with contextlib.suppress(Exception):
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()
        _lock_path().unlink(missing_ok=True)


if __name__ == "__main__":
    supervise()

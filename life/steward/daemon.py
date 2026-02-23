import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from fncli import cli

from .. import telegram as tg
from ..config import LIFE_DIR
from ..lib.errors import echo, exit_error

DAEMON_DIR = LIFE_DIR / "steward"
PID_FILE = DAEMON_DIR / "daemon.pid"
LOG_FILE = DAEMON_DIR / "daemon.log"
MAX_RESPONSE_LEN = 4000
MAX_SPAWNS_PER_HOUR = 12
ALLOWED_CHAT_IDS: set[int] = set()


def _log(msg: str) -> None:
    DAEMON_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a") as f:
        f.write(f"{timestamp} {msg}\n")


def _load_allowed_chats() -> set[int]:
    people_dir = Path.home() / "life" / "steward" / "people"
    chat_ids: set[int] = set()
    if not people_dir.exists():
        return chat_ids
    for profile in people_dir.glob("*.md"):
        try:
            import re

            import yaml

            text = profile.read_text()
            match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
            if not match:
                continue
            frontmatter = yaml.safe_load(match.group(1))
            if isinstance(frontmatter, dict) and frontmatter.get("telegram"):
                chat_ids.add(int(frontmatter["telegram"]))
        except Exception:  # noqa: S112
            continue
    return chat_ids


def _build_prompt(message: str, sender_name: str) -> str:
    return f"""You are Steward responding via Telegram. Be concise — this is a chat message, not a terminal session.

Sender: {sender_name}
Message: {message}

Context: Run `life steward boot` mentally — you have access to all life CLI tools.
Respond directly. No markdown headers. Keep it short and actionable.
If they ask you to do something with the life CLI, do it and confirm.
If it's a question, answer it."""


def _spawn_claude(message: str, sender_name: str) -> str:
    prompt = _build_prompt(message, sender_name)
    cmd = [
        "claude",
        "--print",
        "--dangerously-skip-permissions",
        "--model",
        "claude-sonnet-4-6",
        prompt,
    ]
    env = os.environ.copy()
    env.pop("ANTHROPIC_BASE_URL", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)

    try:
        result = subprocess.run(
            cmd,
            cwd=Path.home() / "life",
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = result.stdout.strip()
        if not output and result.stderr:
            return f"[steward error: {result.stderr[:200]}]"
        if len(output) > MAX_RESPONSE_LEN:
            output = output[:MAX_RESPONSE_LEN] + "\n\n[truncated]"
        return output or "[steward: no response]"
    except subprocess.TimeoutExpired:
        return "[steward: timed out (120s)]"
    except Exception as e:
        return f"[steward error: {e}]"


def _rate_check(spawn_times: list[float]) -> bool:
    now = time.time()
    cutoff = now - 3600
    spawn_times[:] = [t for t in spawn_times if t > cutoff]
    return len(spawn_times) < MAX_SPAWNS_PER_HOUR


def run(interval: int = 10) -> None:
    DAEMON_DIR.mkdir(parents=True, exist_ok=True)

    allowed = _load_allowed_chats()
    if not allowed:
        sys.stdout.write("No people with telegram chat_id found in steward/people/\n")
        sys.exit(1)

    with PID_FILE.open("w") as f:
        f.write(str(os.getpid()))

    running = True
    spawn_times: list[float] = []

    def handle_signal(signum, frame):
        nonlocal running
        running = False
        _log("shutdown signal received")

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    _log(f"daemon started, polling every {interval}s, {len(allowed)} allowed chat(s)")
    sys.stdout.write(f"steward daemon started (PID {os.getpid()})\n")

    while running:
        try:
            messages = tg.poll(timeout=interval)
            for msg in messages:
                chat_id = msg["chat_id"]
                if chat_id not in allowed:
                    _log(f"ignored message from unknown chat {chat_id}")
                    continue

                body = msg["body"]
                sender = msg.get("from_name", "unknown")
                _log(f"[{sender}] {body[:80]}")

                if not _rate_check(spawn_times):
                    tg.send(chat_id, "[steward: rate limited — try again in a bit]")
                    _log("rate limited, skipping spawn")
                    continue

                spawn_times.append(time.time())
                _log(f"spawning claude for: {body[:60]}")
                response = _spawn_claude(body, sender)
                _log(f"response ({len(response)} chars)")

                tg.send(chat_id, response)

        except Exception as e:
            _log(f"poll error: {e}")
            time.sleep(5)

    PID_FILE.unlink(missing_ok=True)
    _log("daemon stopped")


def start(interval: int = 10, foreground: bool = False) -> tuple[bool, str]:
    if is_running():
        return False, f"already running (PID {get_pid()})"

    allowed = _load_allowed_chats()
    if not allowed:
        return False, "no people with telegram chat_id in steward/people/"

    if foreground:
        run(interval)
        return True, "stopped"

    pid = os.fork()
    if pid > 0:
        time.sleep(0.5)
        if is_running():
            return True, f"started (PID {pid})"
        return False, "failed to start"

    os.setsid()
    os.umask(0)

    devnull = Path(os.devnull)
    sys.stdin = devnull.open()
    sys.stdout = devnull.open("w")
    sys.stderr = devnull.open("w")

    run(interval)
    sys.exit(0)


def stop() -> tuple[bool, str]:
    pid = get_pid()
    if not pid:
        return False, "not running"

    try:
        os.kill(pid, signal.SIGTERM)
        for _ in range(10):
            time.sleep(0.5)
            if not is_running():
                return True, "stopped"
        os.kill(pid, signal.SIGKILL)
        PID_FILE.unlink(missing_ok=True)
        return True, "killed"
    except ProcessLookupError:
        PID_FILE.unlink(missing_ok=True)
        return True, "was not running"


def get_pid() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text().strip())
    except (ValueError, FileNotFoundError):
        return None


def is_running() -> bool:
    pid = get_pid()
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        PID_FILE.unlink(missing_ok=True)
        return False


def status() -> dict[str, Any]:
    pid = get_pid()
    running = is_running()

    result: dict[str, Any] = {
        "running": running,
        "pid": pid if running else None,
        "allowed_chats": len(_load_allowed_chats()),
        "log_file": str(LOG_FILE),
    }

    if LOG_FILE.exists():
        lines = LOG_FILE.read_text().strip().split("\n")
        result["last_log"] = lines[-5:] if len(lines) > 5 else lines

    return result


@cli("life steward daemon", name="start")
def daemon_start(foreground: bool = False, interval: int = 10) -> None:
    """Start steward Telegram daemon"""
    ok, msg = start(interval=interval, foreground=foreground)
    echo(msg)
    if not ok:
        exit_error("")


@cli("life steward daemon", name="stop")
def daemon_stop() -> None:
    """Stop steward Telegram daemon"""
    ok, msg = stop()
    echo(msg)
    if not ok:
        exit_error("")


@cli("life steward daemon", name="status")
def daemon_status() -> None:
    """Show steward daemon status"""
    info = status()
    if info["running"]:
        echo(f"running (PID {info['pid']})")
    else:
        echo("not running")
    echo(f"allowed chats: {info['allowed_chats']}")
    if info.get("last_log"):
        echo("\nrecent log:")
        for line in info["last_log"]:
            echo(f"  {line}")

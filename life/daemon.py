import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from fncli import cli

from .config import LIFE_DIR
from .lib.errors import echo, exit_error

DAEMON_DIR = LIFE_DIR
PID_FILE = DAEMON_DIR / "daemon.pid"
LOG_FILE = DAEMON_DIR / "daemon.log"

MAX_TG_SPAWNS_PER_HOUR = 12
MAX_TG_RESPONSE_LEN = 4000
PEOPLE_DIR = Path.home() / "life" / "steward" / "people"


def _log(msg: str) -> None:
    DAEMON_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    entry = f"{timestamp} {msg}\n"
    with LOG_FILE.open("a") as f:
        f.write(entry)


def _load_allowed_tg_chats() -> set[int]:
    import re

    import yaml

    chat_ids: set[int] = set()
    if not PEOPLE_DIR.exists():
        return chat_ids
    for profile in PEOPLE_DIR.glob("*.md"):
        try:
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


def _build_tg_prompt(message: str, sender_name: str) -> str:
    return f"""You are Steward responding via Telegram. Be concise — this is a chat message, not a terminal session.

Sender: {sender_name}
Message: {message}

Context: Run `life steward boot` mentally — you have access to all life CLI tools.
Respond directly. No markdown headers. Keep it short and actionable.
If they ask you to do something with the life CLI, do it and confirm.
If it's a question, answer it."""


def _spawn_claude_tg(message: str, sender_name: str) -> str:
    prompt = _build_tg_prompt(message, sender_name)
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
        if len(output) > MAX_TG_RESPONSE_LEN:
            output = output[:MAX_TG_RESPONSE_LEN] + "\n\n[truncated]"
        return output or "[steward: no response]"
    except subprocess.TimeoutExpired:
        return "[steward: timed out (120s)]"
    except Exception as e:
        return f"[steward error: {e}]"


def _telegram_thread(stop: threading.Event, interval: int) -> None:
    from . import telegram as tg

    allowed = _load_allowed_tg_chats()
    if not allowed:
        _log("[telegram] no people with telegram chat_id — thread disabled")
        return

    spawn_times: list[float] = []
    _log(f"[telegram] started, {len(allowed)} allowed chat(s), polling every {interval}s")

    while not stop.is_set():
        try:
            messages = tg.poll(timeout=interval)
            for msg in messages:
                chat_id = msg["chat_id"]
                if chat_id not in allowed:
                    _log(f"[telegram] ignored unknown chat {chat_id}")
                    continue

                body = msg["body"]
                sender = msg.get("from_name", "unknown")
                _log(f"[telegram] [{sender}] {body[:80]}")

                now = time.time()
                cutoff = now - 3600
                spawn_times[:] = [t for t in spawn_times if t > cutoff]
                if len(spawn_times) >= MAX_TG_SPAWNS_PER_HOUR:
                    tg.send(chat_id, "[steward: rate limited — try again in a bit]")
                    _log("[telegram] rate limited, skipping spawn")
                    continue

                spawn_times.append(now)
                _log(f"[telegram] spawning claude for: {body[:60]}")
                response = _spawn_claude_tg(body, sender)
                _log(f"[telegram] response ({len(response)} chars)")
                tg.send(chat_id, response)

        except Exception as e:
            _log(f"[telegram] poll error: {e}")
            stop.wait(5)


def _get_signal_phones() -> list[str]:
    from .comms import accounts as accts_module

    accounts = accts_module.list_accounts("messaging")
    return [a["email"] for a in accounts if a["provider"] == "signal"]


def _signal_thread(stop: threading.Event, interval: int) -> None:
    from .comms import agent
    from .comms.adapters.messaging import signal as signal_adapter
    from .comms.config import get_agent_config

    phones = _get_signal_phones()
    if not phones:
        _log("[signal] no Signal accounts linked — thread disabled")
        return

    _log(f"[signal] started, {len(phones)} account(s), polling every {interval}s")

    while not stop.is_set():
        agent_config = get_agent_config()
        agent_enabled = bool(agent_config.get("enabled", True))
        use_nlp = bool(agent_config.get("nlp", False))

        for phone in phones:
            try:
                msgs = signal_adapter.receive(timeout=1, phone=phone, store=True)
                if msgs:
                    for m in msgs:
                        sender = m.get("from_name", m.get("sender_phone", "Unknown"))
                        _log(f"[signal] [{phone}] {sender}: {m['body'][:50]}")

                        if agent_enabled:
                            response = agent.handle_incoming(phone, m, use_nlp=use_nlp)
                            if response:
                                sender_phone = m.get("sender_phone", "")
                                if sender_phone:
                                    signal_adapter.send(phone, sender_phone, response)
                                    _log(f"[signal] [{phone}] -> {sender_phone}: {response[:50]}")
            except Exception as e:
                _log(f"[signal] [{phone}] error: {e}")

        stop.wait(interval)


def _auto_thread(stop: threading.Event, every: int, provider: str) -> None:
    from .steward.auto import _run_autonomous

    _log(f"[auto] started, running every {every}s, provider={provider}")

    while not stop.is_set():
        try:
            _log("[auto] starting autonomous loop")
            _run_autonomous(provider=provider)
            _log("[auto] loop complete")
        except Exception as e:
            _log(f"[auto] loop error: {e}")

        stop.wait(every)


def run(
    tg_interval: int = 10,
    signal_interval: int = 5,
    auto_every: int = 0,
    auto_provider: str = "claude",
) -> None:
    DAEMON_DIR.mkdir(parents=True, exist_ok=True)

    with PID_FILE.open("w") as f:
        f.write(str(os.getpid()))

    stop = threading.Event()

    def handle_signal(signum, frame):
        _log("shutdown signal received")
        stop.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    threads: list[threading.Thread] = []

    tg = threading.Thread(
        target=_telegram_thread, args=(stop, tg_interval), daemon=True, name="telegram"
    )
    threads.append(tg)
    tg.start()

    sig = threading.Thread(
        target=_signal_thread, args=(stop, signal_interval), daemon=True, name="signal"
    )
    threads.append(sig)
    sig.start()

    if auto_every > 0:
        auto = threading.Thread(
            target=_auto_thread,
            args=(stop, auto_every, auto_provider),
            daemon=True,
            name="auto",
        )
        threads.append(auto)
        auto.start()

    _log(
        f"daemon started (PID {os.getpid()}) tg_interval={tg_interval}s "
        f"signal_interval={signal_interval}s auto_every={auto_every}s"
    )
    sys.stdout.write(f"life daemon started (PID {os.getpid()})\n")

    stop.wait()

    for t in threads:
        t.join(timeout=5)

    PID_FILE.unlink(missing_ok=True)
    _log("daemon stopped")


def start(
    tg_interval: int = 10,
    signal_interval: int = 5,
    auto_every: int = 0,
    auto_provider: str = "claude",
    foreground: bool = False,
) -> tuple[bool, str]:
    if is_running():
        return False, f"already running (PID {get_pid()})"

    if foreground:
        run(
            tg_interval=tg_interval,
            signal_interval=signal_interval,
            auto_every=auto_every,
            auto_provider=auto_provider,
        )
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

    run(
        tg_interval=tg_interval,
        signal_interval=signal_interval,
        auto_every=auto_every,
        auto_provider=auto_provider,
    )
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
        "allowed_tg_chats": len(_load_allowed_tg_chats()),
        "signal_phones": _get_signal_phones(),
        "log_file": str(LOG_FILE),
    }

    if LOG_FILE.exists():
        lines = LOG_FILE.read_text().strip().split("\n")
        result["last_log"] = lines[-10:] if len(lines) > 10 else lines

    return result


PLIST_NAME = "com.life.daemon.plist"
LAUNCHD_DIR = Path.home() / "Library/LaunchAgents"
PLIST_PATH = LAUNCHD_DIR / PLIST_NAME


def _get_life_path() -> str:
    result = subprocess.run(["which", "life"], capture_output=True, text=True)
    if result.returncode == 0:
        return result.stdout.strip()
    return str(Path(sys.executable).parent / "life")


def _generate_plist(tg_interval: int = 10, signal_interval: int = 5, auto_every: int = 0) -> str:
    life_path = _get_life_path()
    python_path = Path(sys.executable).parent

    args = [
        f"<string>{life_path}</string>",
        "<string>daemon</string>",
        "<string>start</string>",
        "<string>--foreground</string>",
        f"<string>--tg-interval</string><string>{tg_interval}</string>",
        f"<string>--signal-interval</string><string>{signal_interval}</string>",
    ]
    if auto_every > 0:
        args.append(f"<string>--auto-every</string><string>{auto_every}</string>")

    args_xml = "\n        ".join(args)

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.life.daemon</string>
    <key>ProgramArguments</key>
    <array>
        {args_xml}
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{DAEMON_DIR}/launchd.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>{DAEMON_DIR}/launchd.stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>{python_path}:/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
        <key>HOME</key>
        <string>{Path.home()}</string>
    </dict>
</dict>
</plist>
"""


def install(
    tg_interval: int = 10, signal_interval: int = 5, auto_every: int = 0
) -> tuple[bool, str]:
    LAUNCHD_DIR.mkdir(parents=True, exist_ok=True)
    DAEMON_DIR.mkdir(parents=True, exist_ok=True)

    PLIST_PATH.write_text(_generate_plist(tg_interval, signal_interval, auto_every))

    result = subprocess.run(
        ["launchctl", "load", str(PLIST_PATH)],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return False, result.stderr or "failed to load plist"

    return True, f"installed and loaded {PLIST_PATH}"


def uninstall() -> tuple[bool, str]:
    if not PLIST_PATH.exists():
        return False, "not installed"

    subprocess.run(
        ["launchctl", "unload", str(PLIST_PATH)],
        capture_output=True,
        text=True,
    )

    PLIST_PATH.unlink(missing_ok=True)
    return True, "uninstalled"


@cli("life daemon", name="start")
def daemon_start(
    foreground: bool = False,
    tg_interval: int = 10,
    signal_interval: int = 5,
    auto_every: int = 0,
    auto_provider: str = "claude",
) -> None:
    """Start life daemon (Telegram + Signal + optional auto loop)"""
    ok, msg = start(
        tg_interval=tg_interval,
        signal_interval=signal_interval,
        auto_every=auto_every,
        auto_provider=auto_provider,
        foreground=foreground,
    )
    echo(msg)
    if not ok:
        exit_error("")


@cli("life daemon", name="stop")
def daemon_stop() -> None:
    """Stop life daemon"""
    ok, msg = stop()
    echo(msg)
    if not ok:
        exit_error("")


@cli("life daemon", name="status")
def daemon_status() -> None:
    """Show life daemon status"""
    info = status()
    if info["running"]:
        echo(f"running (PID {info['pid']})")
    else:
        echo("not running")
    echo(f"allowed telegram chats: {info['allowed_tg_chats']}")
    echo(f"signal phones: {', '.join(info['signal_phones']) or 'none'}")
    if info.get("last_log"):
        echo("\nrecent log:")
        for line in info["last_log"]:
            echo(f"  {line}")


@cli("life daemon", name="install")
def daemon_install(
    tg_interval: int = 10,
    signal_interval: int = 5,
    auto_every: int = 0,
) -> None:
    """Install life daemon as launchd service (auto-start on boot)"""
    ok, msg = install(
        tg_interval=tg_interval, signal_interval=signal_interval, auto_every=auto_every
    )
    echo(msg)
    if not ok:
        exit_error("")


@cli("life daemon", name="uninstall")
def daemon_uninstall() -> None:
    """Uninstall life daemon launchd service"""
    ok, msg = uninstall()
    echo(msg)
    if not ok:
        exit_error("")

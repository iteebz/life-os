import os
import signal
import subprocess
import threading
import time
from pathlib import Path

from life.config import LIFE_DIR

DAEMON_DIR = LIFE_DIR
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
    from life import telegram as tg

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
    from life.comms import accounts as accts_module

    accounts = accts_module.list_accounts("messaging")
    return [a["email"] for a in accounts if a["provider"] == "signal"]


def _signal_thread(stop: threading.Event, interval: int) -> None:
    from life.comms.adapters.messaging import signal as signal_adapter

    phones = _get_signal_phones()
    if not phones:
        _log("[signal] no Signal accounts linked — thread disabled")
        return

    _log(f"[signal] started, {len(phones)} account(s), polling every {interval}s")

    while not stop.is_set():
        for phone in phones:
            try:
                msgs = signal_adapter.receive(timeout=1, phone=phone, store=True)
                if msgs:
                    for m in msgs:
                        sender = m.get("from_name", m.get("peer", "Unknown"))
                        _log(f"[signal] [{phone}] {sender}: {m['body'][:50]}")
            except Exception as e:
                _log(f"[signal] [{phone}] error: {e}")

        stop.wait(interval)


def _auto_thread(stop: threading.Event, every: int, provider: str) -> None:
    from life.steward.auto import _run_autonomous

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

    stop.wait()

    for t in threads:
        t.join(timeout=5)

    _log("daemon stopped")

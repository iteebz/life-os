import os
import signal
import threading
import time
from datetime import datetime
from pathlib import Path

from life.config import LIFE_DIR
from life.daemon.spawn import fetch_wake_context, spawn_claude

DAEMON_DIR = LIFE_DIR
LOG_FILE = DAEMON_DIR / "daemon.log"

MAX_TG_SPAWNS_PER_HOUR = 12
TG_SESSION_TIMEOUT = 3600  # 1 hour — restart with boot after this
TG_SESSION_MAX_CHARS = 300_000  # ~100k tokens
NUDGE_HOUR = 8  # 8am daily batch
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


def _build_tg_boot_prompt(message: str, sender_name: str, context: str) -> str:
    return f"""\
You are Steward responding via Telegram. New session — run boot sequence first.

Current life state:
{context}

Sender: {sender_name}
Message: {message}

Respond directly. Short and actionable. No markdown headers."""


def _trim_tg_history(history: list[dict[str, str]]) -> list[dict[str, str]]:
    total = 0
    cutoff = len(history)
    for i in range(len(history) - 1, -1, -1):
        total += len(history[i]["text"])
        if total > 8000:
            cutoff = i + 1
            break
    else:
        cutoff = 0
    return history[cutoff:]


def _build_tg_reply_prompt(history: list[dict[str, str]], message: str) -> str:
    recent = _trim_tg_history(history)
    truncated = len(recent) < len(history)
    parts = [
        "You are Steward in a Telegram conversation with Tyson. "
        "Be concise — chat format. You have access to all life CLI tools.\n",
    ]
    if truncated:
        parts.append("[earlier conversation truncated]\n")
    parts.append("Conversation so far:")
    for entry in recent:
        role = "Tyson" if entry["role"] == "user" else "Steward"
        parts.append(f"{role}: {entry['text']}")
    parts.append(f"\nTyson: {message}")
    parts.append("\nRespond directly. Short and actionable. No markdown headers.")
    return "\n".join(parts)


def _telegram_thread(
    stop: threading.Event, interval: int, claimed_chat: threading.Event
) -> None:
    from life.comms.messages import telegram as tg

    allowed = _load_allowed_tg_chats()
    if not allowed:
        _log("[telegram] no people with telegram chat_id — thread disabled")
        return

    spawn_times: list[float] = []
    session_history: list[dict[str, str]] = []
    session_last_time: float = 0.0
    session_chars: int = 0

    _log(f"[telegram] started, {len(allowed)} allowed chat(s), polling every {interval}s")

    while not stop.is_set():
        # nightly session owns the poll loop — back off
        if claimed_chat.is_set():
            stop.wait(2)
            continue

        try:
            from life.nudge import is_quiet_now

            if is_quiet_now():
                stop.wait(60)
                continue

            messages = tg.poll(timeout=interval)
            for msg in messages:
                # re-check: nightly may have claimed between poll return and here
                if claimed_chat.is_set():
                    break

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

                elapsed = now - session_last_time
                continuing = (
                    elapsed < TG_SESSION_TIMEOUT
                    and session_chars < TG_SESSION_MAX_CHARS
                    and bool(session_history)
                )

                if continuing:
                    _log(f"[telegram] continuing session ({session_chars} chars, {elapsed:.0f}s ago)")
                    session_history.append({"role": "user", "text": body})
                    prompt = _build_tg_reply_prompt(session_history, body)
                else:
                    _log(f"[telegram] new session — boot context")
                    session_history = []
                    session_chars = 0
                    context = fetch_wake_context()
                    prompt = _build_tg_boot_prompt(body, sender, context)

                response = spawn_claude(prompt)
                _log(f"[telegram] response ({len(response)} chars)")
                tg.send(chat_id, response)

                if not continuing:
                    session_history = [
                        {"role": "user", "text": body},
                        {"role": "assistant", "text": response},
                    ]
                else:
                    session_history.append({"role": "assistant", "text": response})
                session_chars = sum(len(e["text"]) for e in session_history)
                session_last_time = now

        except Exception as e:
            _log(f"[telegram] poll error: {e}")
            stop.wait(5)


def _get_signal_phones() -> list[str]:
    from life.comms import accounts as accts_module

    accounts = accts_module.list_accounts("messaging")
    return [a["email"] for a in accounts if a["provider"] == "signal"]


def _signal_thread(stop: threading.Event, interval: int) -> None:
    from life.comms.messages import signal as signal_adapter

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


def _nudge_thread(stop: threading.Event) -> None:
    from life.nudge import run_cycle

    _log(f"[nudge] started, activation at {NUDGE_HOUR:02d}:00 daily")
    triggered_today: str | None = None

    while not stop.is_set():
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")

        if now.hour == NUDGE_HOUR and triggered_today != today_str:
            triggered_today = today_str
            try:
                sent = run_cycle()
                _log(f"[nudge] morning batch: sent {sent} nudge(s)")
            except Exception as e:
                _log(f"[nudge] error: {e}")

        stop.wait(30)


def _auto_thread(stop: threading.Event, every: int, provider: str) -> None:
    from life.steward.auto import run_autonomous

    _log(f"[auto] started, running every {every}s, provider={provider}")

    while not stop.is_set():
        try:
            _log("[auto] starting autonomous loop")
            run_autonomous(provider=provider)
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
    from life.daemon.nightly import nightly_thread

    DAEMON_DIR.mkdir(parents=True, exist_ok=True)

    stop = threading.Event()
    claimed_chat = threading.Event()

    def handle_signal(signum, frame):
        _log("shutdown signal received")
        stop.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    threads: list[threading.Thread] = []

    tg = threading.Thread(
        target=_telegram_thread, args=(stop, tg_interval, claimed_chat), daemon=True, name="telegram"
    )
    threads.append(tg)
    tg.start()

    nightly = threading.Thread(
        target=nightly_thread, args=(stop, claimed_chat), daemon=True, name="nightly"
    )
    threads.append(nightly)
    nightly.start()

    sig = threading.Thread(
        target=_signal_thread, args=(stop, signal_interval), daemon=True, name="signal"
    )
    threads.append(sig)
    sig.start()

    nudge = threading.Thread(
        target=_nudge_thread, args=(stop,), daemon=True, name="nudge"
    )
    threads.append(nudge)
    nudge.start()

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
        f"signal_interval={signal_interval}s auto_every={auto_every}s "
        f"nudge=08:00 nightly=20:00"
    )

    stop.wait()

    for t in threads:
        t.join(timeout=5)

    _log("daemon stopped")

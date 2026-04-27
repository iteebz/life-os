import os
import signal
import threading
import time

from life.daemon.shared import (
    DAEMON_DIR,
    MAX_TG_SPAWNS_PER_HOUR,
    PEOPLE_DIR,
    TG_SESSION_MAX_CHARS,
    TG_SESSION_TIMEOUT,
    log,
)
from life.daemon.spawn import fetch_wake_context, spawn_claude


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

Respond directly. Start with 🌱. Short and actionable. No markdown headers."""


def _telegram_thread(
    stop: threading.Event, interval: int, claimed_chat: threading.Event
) -> None:
    from life.comms.messages import telegram as tg
    from life.daemon.commands import handle_command
    from life.daemon.session import build_reply_prompt

    allowed = _load_allowed_tg_chats()
    if not allowed:
        log("[telegram] no people with telegram chat_id — thread disabled")
        return

    spawn_times: list[float] = []
    session_history: list[dict[str, str]] = []
    session_last_time: float = 0.0
    session_chars: int = 0

    log(f"[telegram] started, {len(allowed)} allowed chat(s), polling every {interval}s")

    while not stop.is_set():
        # scheduled session owns the poll loop — back off
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
                if claimed_chat.is_set():
                    break

                chat_id = msg["chat_id"]
                if chat_id not in allowed:
                    log(f"[telegram] ignored unknown chat {chat_id}")
                    continue

                body = msg["body"]
                sender = msg.get("from_name", "unknown")
                log(f"[telegram] [{sender}] {body[:80]}")

                # slash commands — instant, no spawn
                if body.startswith("/"):
                    resp = handle_command(body, session_history, session_last_time, session_chars)
                    if resp is not None:
                        tg.send(chat_id, resp)
                        log(f"[telegram] command: {body.split()[0]}")
                        continue

                now = time.time()
                cutoff = now - 3600
                spawn_times[:] = [t for t in spawn_times if t > cutoff]
                if len(spawn_times) >= MAX_TG_SPAWNS_PER_HOUR:
                    tg.send(chat_id, "🌱 rate limited — try again in a bit")
                    log("[telegram] rate limited, skipping spawn")
                    continue

                spawn_times.append(now)

                elapsed = now - session_last_time
                continuing = (
                    elapsed < TG_SESSION_TIMEOUT
                    and session_chars < TG_SESSION_MAX_CHARS
                    and bool(session_history)
                )

                if continuing:
                    log(f"[telegram] continuing session ({session_chars} chars, {elapsed:.0f}s ago)")
                    session_history.append({"role": "user", "text": body})
                    prompt = build_reply_prompt(session_history, body)
                else:
                    log("[telegram] new session — boot context")
                    session_history = []
                    session_chars = 0
                    context = fetch_wake_context()
                    prompt = _build_tg_boot_prompt(body, sender, context)

                photo = msg.get("photo_path")
                response = spawn_claude(prompt, photo_path=photo)
                log(f"[telegram] response ({len(response)} chars)")
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
            log(f"[telegram] poll error: {e}")
            stop.wait(5)


def _get_signal_phones() -> list[str]:
    from life.comms import accounts as accts_module

    accounts = accts_module.list_accounts("messaging")
    return [a["email"] for a in accounts if a["provider"] == "signal"]


def _signal_thread(stop: threading.Event, interval: int) -> None:
    from life.comms.messages import signal as signal_adapter

    phones = _get_signal_phones()
    if not phones:
        log("[signal] no Signal accounts linked — thread disabled")
        return

    log(f"[signal] started, {len(phones)} account(s), polling every {interval}s")

    while not stop.is_set():
        for phone in phones:
            try:
                msgs = signal_adapter.receive(timeout=1, phone=phone, store=True)
                if msgs:
                    for m in msgs:
                        sender = m.get("from_name", m.get("peer", "Unknown"))
                        log(f"[signal] [{phone}] {sender}: {m['body'][:50]}")
            except Exception as e:
                log(f"[signal] [{phone}] error: {e}")

        stop.wait(interval)



def _auto_thread(stop: threading.Event, every: int) -> None:
    from life.steward.auto import run_autonomous

    log(f"[auto] started, running every {every}s")

    while not stop.is_set():
        try:
            log("[auto] starting autonomous loop")
            run_autonomous()
            log("[auto] loop complete")
        except Exception as e:
            log(f"[auto] loop error: {e}")

        stop.wait(every)


def run(
    tg_interval: int = 10,
    signal_interval: int = 5,
    auto_every: int = 0,
) -> None:
    from life.daemon.morning import morning_thread

    DAEMON_DIR.mkdir(parents=True, exist_ok=True)

    stop = threading.Event()
    claimed_chat = threading.Event()

    def handle_signal(signum, frame):
        log("shutdown signal received")
        stop.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    threads: list[threading.Thread] = []

    tg = threading.Thread(
        target=_telegram_thread, args=(stop, tg_interval, claimed_chat), daemon=True, name="telegram"
    )
    threads.append(tg)
    tg.start()

    morning = threading.Thread(
        target=morning_thread, args=(stop, claimed_chat), daemon=True, name="morning"
    )
    threads.append(morning)
    morning.start()

    sig = threading.Thread(
        target=_signal_thread, args=(stop, signal_interval), daemon=True, name="signal"
    )
    threads.append(sig)
    sig.start()

    if auto_every > 0:
        auto = threading.Thread(
            target=_auto_thread,
            args=(stop, auto_every),
            daemon=True,
            name="auto",
        )
        threads.append(auto)
        auto.start()

    log(
        f"daemon started (PID {os.getpid()}) tg_interval={tg_interval}s "
        f"signal_interval={signal_interval}s auto_every={auto_every}s "
        f"morning=08:00"
    )

    stop.wait()

    for t in threads:
        t.join(timeout=5)

    log("daemon stopped")

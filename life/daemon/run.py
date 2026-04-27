import os
import re
import signal
import threading
import time

import yaml

import life.daemon.shared as shared
from life.comms import accounts as accts_module
from life.comms.messages import signal as signal_adapter
from life.comms.messages import telegram as tg
from life.daemon.commands import handle_command
from life.daemon.inbound import catch_up, mark_read_for_session
from life.daemon.inbound import handle as handle_inbound
from life.daemon.morning import morning_thread
from life.daemon.reap import sweep as reap_sweep
from life.daemon.session import get_tyson_chat_id
from life.daemon.shared import (
    DAEMON_DIR,
    MAX_TG_SPAWNS_PER_HOUR,
    PEOPLE_DIR,
    log,
)
from life.lib.clock import is_quiet_now
from life.steward.auto import run_autonomous


def _load_allowed_tg_chats() -> set[int]:
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


def _telegram_thread(
    stop: threading.Event, interval: int, claimed_chat: threading.Event
) -> None:
    allowed = _load_allowed_tg_chats()
    if not allowed:
        log("[telegram] no people with telegram chat_id — thread disabled")
        return

    spawn_times: list[float] = []

    log(f"[telegram] started, {len(allowed)} allowed chat(s), polling every {interval}s")

    while not stop.is_set():
        if claimed_chat.is_set():
            stop.wait(2)
            continue

        try:
            if is_quiet_now():
                stop.wait(60)
                continue

            messages = tg.poll(timeout=interval)

            # Group by chat_id so a burst of messages → one spawn, not many
            batched: dict[int, list[dict[str, object]]] = {}
            for msg in messages:
                if claimed_chat.is_set():
                    break
                chat_id = msg["chat_id"]
                if chat_id not in allowed:
                    log(f"[telegram] ignored unknown chat {chat_id}")
                    continue
                batched.setdefault(chat_id, []).append(msg)

            for chat_id, chat_msgs in batched.items():
                if claimed_chat.is_set():
                    break

                # Handle slash commands immediately, remove them from batch
                remaining = []
                for msg in chat_msgs:
                    body = str(msg["body"])
                    if body.startswith("/"):
                        resp = handle_command(body, [], 0.0, 0)
                        if resp is not None:
                            tg.send(chat_id, resp)
                            log(f"[telegram] command: {body.split(maxsplit=1)[0]}")
                    else:
                        remaining.append(msg)

                if not remaining:
                    continue

                now = time.time()
                cutoff = now - 3600
                spawn_times[:] = [t for t in spawn_times if t > cutoff]
                if len(spawn_times) >= MAX_TG_SPAWNS_PER_HOUR:
                    tg.send(chat_id, "🌱 rate limited — try again in a bit")
                    log("[telegram] rate limited, skipping spawn")
                    continue

                sender = remaining[-1].get("from_name", "unknown")
                if len(remaining) == 1:
                    body = remaining[0]["body"]
                else:
                    body = "\n".join(m["body"] for m in remaining)
                    log(f"[telegram] bundling {len(remaining)} messages from {sender}")

                log(f"[telegram] [{sender}] {body[:80]}")
                spawn_times.append(now)
                action = handle_inbound("telegram", sender, body, chat_id=chat_id)
                if action in ("responded", "resumed"):
                    mark_read_for_session(chat_id)
                log(f"[telegram] inbound → {action}")

        except Exception as e:
            log(f"[telegram] poll error: {e}")
            stop.wait(5)


def _get_signal_phones() -> list[str]:
    accounts = accts_module.list_accounts("messaging")
    return [a["email"] for a in accounts if a["provider"] == "signal"]


def _signal_thread(stop: threading.Event, interval: int) -> None:
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
                        action = handle_inbound("signal", sender, m["body"])
                        log(f"[signal] inbound → {action}")
            except Exception as e:
                log(f"[signal] [{phone}] error: {e}")

        stop.wait(interval)


def _reap_thread(stop: threading.Event) -> None:
    log("[reap] started, sweeping every 10s")
    while not stop.is_set():
        try:
            reap_sweep()
        except Exception as e:
            log(f"[reap] error: {e}")
        stop.wait(10)


def _auto_thread(stop: threading.Event, every: int) -> None:
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
    DAEMON_DIR.mkdir(parents=True, exist_ok=True)
    shared.DAEMON_START_TIME = time.time()

    stop = threading.Event()
    claimed_chat = threading.Event()

    def handle_signal(signum, frame):
        log("shutdown signal received")
        stop.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    threads: list[threading.Thread] = []

    # Catch up on unread messages in a background thread — never block startup.
    def _catchup_thread() -> None:
        tyson_chat = get_tyson_chat_id()
        if not tyson_chat or is_quiet_now():
            return
        try:
            action = catch_up(tyson_chat)
            if action == "caught_up":
                log("[startup] caught up on unread messages")
        except Exception as e:
            log(f"[startup] catch-up failed: {e}")

    catchup = threading.Thread(target=_catchup_thread, daemon=True, name="catchup")
    threads.append(catchup)
    catchup.start()

    tg_thread = threading.Thread(
        target=_telegram_thread, args=(stop, tg_interval, claimed_chat), daemon=True, name="telegram"
    )
    threads.append(tg_thread)
    tg_thread.start()

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

    reap = threading.Thread(
        target=_reap_thread, args=(stop,), daemon=True, name="reap"
    )
    threads.append(reap)
    reap.start()

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

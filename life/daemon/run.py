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
from life.daemon.inbound import handle as handle_inbound
from life.daemon.morning import morning_thread
from life.daemon.reap import sweep as reap_sweep
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
                    cutoff_cmd = time.time() - 3600
                    active_spawns = sum(1 for t in spawn_times if t > cutoff_cmd)
                    resp = handle_command(body, [], 0.0, 0, active_spawns)
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
                action = handle_inbound("telegram", sender, body, chat_id=chat_id)
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

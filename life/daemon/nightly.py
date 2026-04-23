"""Nightly steward activation — 8pm proactive check-in via Telegram."""

import threading
from datetime import datetime

from life.daemon.session import get_tyson_chat_id, run_session
from life.daemon.shared import log
from life.daemon.spawn import fetch_wake_context

NIGHTLY_HOUR = 20


def _build_opener() -> str:
    wake = fetch_wake_context()
    return (
        "You are Steward. It's the 8pm nightly check-in via Telegram.\n\n"
        f"Current life state:\n{wake}\n\n"
        "Send Tyson a short evening sitrep: what got done, what's open, "
        "one thing to close tonight if he has energy.\n\n"
        "Casual and short. Telegram message, not a report. "
        "Start with 🌱. No markdown headers. No bullet symbols. Plain text only."
    )


def trigger_now() -> None:
    """Manual trigger — runs a nightly session in the foreground.
    Refuses if daemon is already running (would fight over polls)."""
    from life.daemon.cli import _pid

    if _pid():
        print("daemon is running — stop it first or let the nightly thread handle it")
        return

    chat_id = get_tyson_chat_id()
    if not chat_id:
        print("no telegram chat_id for tyson")
        return

    stop = threading.Event()
    claimed = threading.Event()
    print(f"triggering nightly session (chat_id={chat_id})")
    try:
        opener = _build_opener()
        run_session(chat_id, opener, stop, claimed, label="nightly")
    except KeyboardInterrupt:
        stop.set()
        claimed.clear()
        print("\nsession interrupted")


def nightly_thread(stop: threading.Event, claimed_chat: threading.Event) -> None:
    chat_id = get_tyson_chat_id()
    if not chat_id:
        log("[nightly] no telegram chat_id for tyson — disabled")
        return

    log(f"[nightly] thread started, activation at {NIGHTLY_HOUR}:00")
    triggered_today: str | None = None

    while not stop.is_set():
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")

        if now.hour == NIGHTLY_HOUR and triggered_today != today_str:
            triggered_today = today_str
            opener = _build_opener()
            run_session(chat_id, opener, stop, claimed_chat, label="nightly")

        stop.wait(30)

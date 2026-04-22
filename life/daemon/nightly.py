"""Nightly steward activation — 8pm proactive check-in via Telegram."""

import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from life.daemon.run import _log
from life.daemon.spawn import spawn_claude

NIGHTLY_HOUR = 20  # 8pm
SESSION_TIMEOUT = 3600  # 1 hour
POLL_INTERVAL = 5
MAX_HISTORY_CHARS = 8000  # ~2k tokens — keeps prompt fast
HISTORY_LOOKBACK_HOURS = 2  # load recent DB messages on session start


def _get_chat_id() -> int | None:
    from life.lib.resolve import resolve_people_field

    result = resolve_people_field("tyson", "telegram")
    return int(result) if result else None


def _fetch_wake_context() -> str:
    """Run `life steward wake` and capture output for prompt injection."""
    try:
        result = subprocess.run(
            ["life", "steward", "wake"],
            cwd=Path.home() / "life",
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout.strip()
    except Exception as e:
        return f"(wake context unavailable: {e})"


def _load_history_from_db(chat_id: int, hours: int = HISTORY_LOOKBACK_HOURS) -> list[dict[str, str]]:
    """Load recent telegram messages from the DB to survive daemon restarts."""
    try:
        from life.lib.store import get_db

        cutoff = int(time.time()) - (hours * 3600)
        with get_db() as conn:
            rows = conn.execute(
                "SELECT direction, body, timestamp FROM messages "
                "WHERE channel = 'telegram' AND peer = ? AND timestamp > ? "
                "ORDER BY timestamp ASC",
                (str(chat_id), cutoff),
            ).fetchall()
        return [
            {"role": "user" if row[0] == "in" else "assistant", "text": row[1]}
            for row in rows
        ]
    except Exception as e:
        _log(f"[nightly] history load failed: {e}")
        return []


def _trim_history(history: list[dict[str, str]]) -> list[dict[str, str]]:
    """Keep most recent entries that fit within MAX_HISTORY_CHARS."""
    total = 0
    cutoff = len(history)
    for i in range(len(history) - 1, -1, -1):
        total += len(history[i]["text"])
        if total > MAX_HISTORY_CHARS:
            cutoff = i + 1
            break
    else:
        cutoff = 0
    return history[cutoff:]


def _build_initial_prompt(wake_context: str) -> str:
    return (
        "You are Steward. It's the 8pm nightly check-in via Telegram.\n\n"
        f"Current life state:\n{wake_context}\n\n"
        "Send Tyson a short evening sitrep: what got done, what's open, "
        "one thing to close tonight if he has energy.\n\n"
        "Casual and short. Telegram message, not a report. "
        "No markdown headers. No bullet symbols. Plain text only."
    )


def _build_reply_prompt(history: list[dict[str, str]], new_message: str) -> str:
    recent = _trim_history(history)
    truncated = len(recent) < len(history)

    parts = [
        "You are Steward in a nightly Telegram check-in with Tyson. "
        "Be concise — chat format. You have access to all life CLI tools.\n",
    ]
    if truncated:
        parts.append("[earlier conversation truncated]\n")
    parts.append("Conversation so far:")
    for entry in recent:
        role = "Tyson" if entry["role"] == "user" else "Steward"
        parts.append(f"{role}: {entry['text']}")

    parts.append(f"\nTyson just said: {new_message}")
    parts.append("\nRespond directly. Short and actionable. No markdown headers.")

    return "\n".join(parts)


def _run_nightly_session(
    chat_id: int, stop: threading.Event, claimed_chat: threading.Event
) -> None:
    from life.comms.messages import telegram as tg

    _log("[nightly] starting session")
    claimed_chat.set()

    # load any recent history from DB (survives restarts)
    history = _load_history_from_db(chat_id)
    if history:
        _log(f"[nightly] loaded {len(history)} messages from DB")

    # pre-fetch context before spawning
    wake_context = _fetch_wake_context()
    prompt = _build_initial_prompt(wake_context)
    response = spawn_claude(prompt)
    tg.send(chat_id, response)
    _log(f"[nightly] sitrep sent ({len(response)} chars)")

    history.append({"role": "assistant", "text": response})
    last_activity = time.time()

    while not stop.is_set():
        elapsed = time.time() - last_activity
        if elapsed > SESSION_TIMEOUT:
            _log("[nightly] session timed out (1hr)")
            break

        messages = tg.poll(timeout=POLL_INTERVAL)
        for msg in messages:
            if msg["chat_id"] != chat_id:
                continue

            body = msg["body"]
            _log(f"[nightly] reply: {body[:80]}")
            last_activity = time.time()

            history.append({"role": "user", "text": body})
            prompt = _build_reply_prompt(history, body)
            reply = spawn_claude(prompt)
            history.append({"role": "assistant", "text": reply})

            tg.send(chat_id, reply)
            _log(f"[nightly] responded ({len(reply)} chars)")

    claimed_chat.clear()
    _log("[nightly] session ended")


def trigger_now() -> None:
    """Manual trigger — runs a nightly session in the foreground.
    Refuses if daemon is already running (would fight over polls)."""
    from life.daemon.cli import _pid

    if _pid():
        print("daemon is running — stop it first or let the nightly thread handle it")
        return

    chat_id = _get_chat_id()
    if not chat_id:
        print("no telegram chat_id for tyson")
        return

    stop = threading.Event()
    claimed = threading.Event()
    print(f"triggering nightly session (chat_id={chat_id})")
    try:
        _run_nightly_session(chat_id, stop, claimed)
    except KeyboardInterrupt:
        stop.set()
        claimed.clear()
        print("\nsession interrupted")


def nightly_thread(stop: threading.Event, claimed_chat: threading.Event) -> None:
    chat_id = _get_chat_id()
    if not chat_id:
        _log("[nightly] no telegram chat_id for tyson — disabled")
        return

    _log(f"[nightly] thread started, activation at {NIGHTLY_HOUR}:00")
    triggered_today: str | None = None

    while not stop.is_set():
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")

        if now.hour == NIGHTLY_HOUR and triggered_today != today_str:
            triggered_today = today_str
            _run_nightly_session(chat_id, stop, claimed_chat)

        stop.wait(30)

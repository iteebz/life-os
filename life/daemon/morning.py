"""Morning + nightly steward sessions via Telegram.

Morning: fires once at 8am unconditionally.
Nightly: fires once at 9pm ONLY if tyson was active today (sent a telegram message).
"""

import time
import threading
from datetime import datetime

from life.daemon.session import get_tyson_chat_id, run_session
from life.daemon.shared import log
from life.daemon.spawn import fetch_wake_context

MORNING_HOUR = 8
NIGHTLY_HOUR = 20


def _gather_nudge_context() -> str:
    from life.lib.clock import now
    from life.nudge import evaluate_rules

    candidates = evaluate_rules(now())
    if not candidates:
        return ""
    lines = [f"- {n.message}" for n in candidates[:5]]
    return "Pending nudges:\n" + "\n".join(lines)


def _load_memory() -> str:
    from pathlib import Path
    memory_path = Path.home() / "life" / "steward" / "memory.md"
    return memory_path.read_text().strip() if memory_path.exists() else ""


def _build_opener() -> str:
    wake = fetch_wake_context()
    nudges = _gather_nudge_context()
    memory = _load_memory()
    parts = [f"Current life state:\n{wake}"]
    if memory:
        parts.append(f"\nSteward memory:\n{memory}")
    if nudges:
        parts.append(f"\n{nudges}")
    parts.append(
        "\n<brief>"
        "\nObjective: consolidated morning brief via Telegram. It's 8am."
        "\nThis is Tyson's only unprompted message today. Make it count."
        "\nInclude: one thing worth knowing, overdue items (if any), one nudge."
        "\nStart with 🌱. Plain text only. 2-3 sentences max."
        "\n</brief>"
    )
    return "\n".join(parts)


def _build_nightly_opener() -> str:
    wake = fetch_wake_context()
    memory = _load_memory()
    parts = [f"Current life state:\n{wake}"]
    if memory:
        parts.append(f"\nSteward memory:\n{memory}")
    parts.append(
        "\n<brief>"
        "\nObjective: end-of-day check-in via Telegram. It's 8pm."
        "\nTyson was active today. Reflect what got done, what didn't."
        "\nIf something important slipped, name it. If the day was good, say so."
        "\nStart with 🌙. Plain text only. 2-3 sentences max."
        "\n</brief>"
    )
    return "\n".join(parts)


def _tyson_active_today(chat_id: int) -> bool:
    """Check if tyson sent any telegram messages today."""
    from life.comms.messages.telegram import get_history

    now = time.time()
    midnight = now - (datetime.now().hour * 3600 + datetime.now().minute * 60 + datetime.now().second)
    hours_since_midnight = max(1, int((now - midnight) / 3600))
    msgs = get_history(chat_id=chat_id, limit=5, hours=hours_since_midnight)
    return any(m["direction"] == "in" for m in msgs)


def morning_thread(stop: threading.Event, claimed_chat: threading.Event) -> None:
    chat_id = get_tyson_chat_id()
    if not chat_id:
        log("[morning] no telegram chat_id for tyson — disabled")
        return

    log(f"[morning] thread started, morning={MORNING_HOUR}:00 nightly={NIGHTLY_HOUR}:00")
    morning_triggered: str | None = None
    nightly_triggered: str | None = None

    while not stop.is_set():
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")

        if now.hour == MORNING_HOUR and morning_triggered != today_str:
            morning_triggered = today_str
            if not claimed_chat.is_set():
                opener = _build_opener()
                run_session(
                    chat_id, opener, stop, claimed_chat,
                    label="morning", tone="Soft morning tone.",
                )

        if now.hour == NIGHTLY_HOUR and nightly_triggered != today_str:
            nightly_triggered = today_str
            if not claimed_chat.is_set() and _tyson_active_today(chat_id):
                log("[nightly] tyson was active today — triggering")
                opener = _build_nightly_opener()
                run_session(
                    chat_id, opener, stop, claimed_chat,
                    label="nightly", tone="Warm wind-down tone.",
                )
            elif not _tyson_active_today(chat_id):
                log("[nightly] tyson off-grid today — skipping")

        stop.wait(30)

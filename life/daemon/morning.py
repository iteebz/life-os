"""Morning steward brief — 8am soft check-in via Telegram."""

import threading
from datetime import datetime

from life.daemon.session import get_tyson_chat_id, run_session
from life.daemon.shared import log
from life.daemon.spawn import fetch_wake_context

MORNING_HOUR = 8


def _gather_nudge_context() -> str:
    from life.lib.clock import now
    from life.nudge import evaluate_rules

    candidates = evaluate_rules(now())
    if not candidates:
        return ""
    lines = [f"- {n.message}" for n in candidates[:5]]
    return "Pending nudges:\n" + "\n".join(lines)


def _build_opener() -> str:
    wake = fetch_wake_context()
    nudges = _gather_nudge_context()
    parts = [f"Current life state:\n{wake}"]
    if nudges:
        parts.append(f"\n{nudges}")
    parts.append(
        "\n<brief>"
        "\nObjective: morning brief via Telegram. It's 8am."
        "\nGood morning brief: soft entry, one thing worth knowing, one nudge if something's due."
        "\nDon't dump tasks. Start with 🌱. Plain text only. 2-3 sentences."
        "\n</brief>"
    )
    return "\n".join(parts)


def morning_thread(stop: threading.Event, claimed_chat: threading.Event) -> None:
    chat_id = get_tyson_chat_id()
    if not chat_id:
        log("[morning] no telegram chat_id for tyson — disabled")
        return

    log(f"[morning] thread started, activation at {MORNING_HOUR}:00")
    triggered_today: str | None = None

    while not stop.is_set():
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")

        if now.hour == MORNING_HOUR and triggered_today != today_str:
            triggered_today = today_str
            if not claimed_chat.is_set():
                opener = _build_opener()
                run_session(
                    chat_id, opener, stop, claimed_chat,
                    label="morning", tone="Soft morning tone.",
                )

        stop.wait(30)

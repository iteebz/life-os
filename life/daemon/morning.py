"""Morning steward brief — single daily Telegram touchpoint.

Fires once at 8am. If Tyson replies before 8pm, steward responds.
No nightly session. No standalone nudges. Everything in one place.
"""

import threading
from datetime import datetime

from life.daemon.session import get_tyson_chat_id, run_session
from life.daemon.shared import log
from life.daemon.spawn import fetch_wake_context

MORNING_HOUR = 8
CUTOFF_HOUR = 20  # replies after 8pm won't trigger a new session


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

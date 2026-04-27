"""Shared Telegram session loop — one implementation, multiple openers."""

import threading
import time
from datetime import datetime
from pathlib import Path

from life.comms.messages import telegram as tg
from life.daemon.commands import handle_command
from life.daemon.shared import TG_SESSION_TIMEOUT, log
from life.daemon.spawn import spawn_claude
from life.lib.clock import is_quiet_now
from life.lib.resolve import resolve_people_field
from life.lib.store import get_db


def load_memory() -> str:
    memory_path = Path.home() / "life" / "steward" / "memory.md"
    if memory_path.exists():
        return memory_path.read_text().strip()
    return ""


def build_tg_boot_prompt(message: str, sender_name: str, context: str) -> str:
    memory = load_memory()
    memory_block = f"\n\nSteward memory:\n{memory}\n" if memory else ""
    return f"""\
You are Steward responding via Telegram. New session — run boot sequence first.

Current life state:
{context}{memory_block}

Sender: {sender_name}
Message: {message}

Respond directly. Start with 🌱. Short and actionable. No markdown headers."""

MAX_HISTORY_CHARS = 8000
POLL_INTERVAL = 5
HISTORY_LOOKBACK_HOURS = 2


def trim_history(history: list[dict[str, str]]) -> list[dict[str, str]]:
    """Keep most recent entries within MAX_HISTORY_CHARS."""
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


def build_reply_prompt(
    history: list[dict[str, str]], message: str, tone: str = ""
) -> str:
    recent = trim_history(history)
    truncated = len(recent) < len(history)
    tone_str = f" {tone}" if tone else ""
    parts = [
        "You are Steward in a Telegram conversation with Tyson. "
        f"Be concise — chat format.{tone_str} You have access to all life CLI tools.\n",
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


def load_history_from_db(chat_id: int, hours: int = HISTORY_LOOKBACK_HOURS) -> list[dict[str, str]]:
    """Load recent telegram messages from DB to survive daemon restarts."""
    try:
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
        log(f"[session] history load failed: {e}")
        return []


def get_tyson_chat_id() -> int | None:
    result = resolve_people_field("tyson", "telegram")
    return int(result) if result else None


def run_session(
    chat_id: int,
    opener: str,
    stop: threading.Event,
    claimed_chat: threading.Event,
    label: str,
    tone: str = "",
    load_db_history: bool = True,
) -> None:
    """Run a full Telegram session: send opener, poll for replies, respond.

    Args:
        chat_id: Telegram chat to interact with.
        opener: Initial prompt for Claude (produces the first message).
        stop: Daemon shutdown event.
        claimed_chat: Mutex — set while this session owns the poll loop.
        label: Log prefix, e.g. "morning", "nightly".
        tone: Extra tone instruction injected into reply prompts.
        load_db_history: Whether to seed history from DB (survives restarts).
    """
    log(f"[{label}] starting session")
    claimed_chat.set()

    history: list[dict[str, str]] = []
    if load_db_history:
        history = load_history_from_db(chat_id)
        if history:
            log(f"[{label}] loaded {len(history)} messages from DB")

    result = spawn_claude(opener)
    tg.send(chat_id, result.text)
    log(f"[{label}] opener sent ({len(result.text)} chars)")

    history.append({"role": "assistant", "text": result.text})
    last_activity = time.time()

    while not stop.is_set():
        if is_quiet_now():
            log(f"[{label}] quiet hours — ending session")
            break

        elapsed = time.time() - last_activity
        if elapsed > TG_SESSION_TIMEOUT:
            log(f"[{label}] session timed out (1hr)")
            break

        messages = tg.poll(timeout=POLL_INTERVAL)
        for msg in messages:
            if msg["chat_id"] != chat_id:
                continue

            body = msg["body"]

            # slash commands inside sessions
            if body.startswith("/"):
                chars = sum(len(e["text"]) for e in history)
                resp = handle_command(body, history, last_activity, chars)
                if resp is not None:
                    tg.send(chat_id, resp)
                    log(f"[{label}] command: {body.split()[0]}")
                    continue

            log(f"[{label}] reply: {body[:80]}")
            last_activity = time.time()

            history.append({"role": "user", "text": body})
            prompt = build_reply_prompt(history, body, tone=tone)
            image = msg.get("image_path")
            result = spawn_claude(prompt, image_path=image)
            history.append({"role": "assistant", "text": result.text})

            tg.send(chat_id, result.text)
            log(f"[{label}] responded ({len(result.text)} chars)")

    claimed_chat.clear()
    from life.daemon.inbound import mark_read_for_session
    mark_read_for_session(chat_id)
    log_session(label, history)
    log(f"[{label}] session ended")


def log_session(label: str, history: list[dict[str, str]]) -> None:
    """Write session transcript to steward/sessions/ for traceability."""
    sessions_dir = Path.home() / "life" / "steward" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    filename = now.strftime(f"%Y-%m-%d-%H%M-{label}.md")
    path = sessions_dir / filename

    lines = [f"# {label} session — {now.strftime('%Y-%m-%d %H:%M')}", ""]
    msg_count = 0
    for entry in history:
        role = "Tyson" if entry["role"] == "user" else "Steward"
        lines.append(f"**{role}:** {entry['text']}")
        lines.append("")
        msg_count += 1

    if msg_count == 0:
        return  # don't log empty sessions

    try:
        path.write_text("\n".join(lines))
        log(f"[{label}] session logged to {path.name}")
    except Exception as e:
        log(f"[{label}] session log failed: {e}")

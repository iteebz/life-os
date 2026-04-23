"""Telegram slash commands — instant responses, no Claude spawn."""

import time

from life.daemon.shared import TG_SESSION_MAX_CHARS, TG_SESSION_TIMEOUT


def handle_command(
    command: str,
    session_history: list[dict[str, str]],
    session_last_time: float,
    session_chars: int,
) -> str | None:
    """Return a response string if command is handled, else None."""
    cmd = command.strip().split()[0].lower() if command.strip() else ""

    if cmd == "/ctx":
        return _cmd_ctx(session_chars)
    if cmd == "/stats":
        return _cmd_stats()
    if cmd == "/session":
        return _cmd_session(session_history, session_last_time, session_chars)
    if cmd == "/help":
        return _cmd_help()
    return None


def _cmd_ctx(session_chars: int) -> str:
    pct = (session_chars / TG_SESSION_MAX_CHARS) * 100
    bar_len = 20
    filled = int(pct / 100 * bar_len)
    bar = "█" * filled + "░" * (bar_len - filled)
    return f"🌱 ctx [{bar}] {pct:.0f}%\n{session_chars:,} / {TG_SESSION_MAX_CHARS:,} chars"


def _cmd_stats() -> str:
    lines = ["🌱 stats"]
    try:
        from life.task import get_tasks

        tasks = get_tasks()
        open_count = len(tasks)
        tags: dict[str, int] = {}
        for t in tasks:
            for tag in t.tags or []:
                tags[tag] = tags.get(tag, 0) + 1
        lines.append(f"open tasks: {open_count}")
        if tags:
            top = sorted(tags.items(), key=lambda x: -x[1])[:5]
            lines.append(" ".join(f"#{t}({n})" for t, n in top))
    except Exception:
        lines.append("tasks: unavailable")

    try:
        from life.mood import get_recent_moods

        moods = get_recent_moods(hours=72)
        if moods:
            avg = sum(m.score for m in moods) / len(moods)
            latest = moods[0]
            label = f" ({latest.label})" if latest.label else ""
            lines.append(f"mood: {latest.score}/5{label} | 3d avg: {avg:.1f}")
        else:
            lines.append("mood: no recent entries")
    except Exception:
        lines.append("mood: unavailable")

    return "\n".join(lines)


def _cmd_session(
    history: list[dict[str, str]],
    last_time: float,
    chars: int,
) -> str:
    if not history:
        return "🌱 no active session"

    elapsed = time.time() - last_time
    remaining = max(0, TG_SESSION_TIMEOUT - elapsed)
    msg_count = len(history)
    user_msgs = sum(1 for h in history if h["role"] == "user")
    return (
        f"🌱 session\n"
        f"messages: {msg_count} ({user_msgs} you, {msg_count - user_msgs} steward)\n"
        f"chars: {chars:,}\n"
        f"timeout in: {int(remaining // 60)}m {int(remaining % 60)}s"
    )


def _cmd_help() -> str:
    return (
        "🌱 commands\n"
        "/ctx — context utilization\n"
        "/stats — tasks, mood\n"
        "/session — active session info\n"
        "/help — this"
    )

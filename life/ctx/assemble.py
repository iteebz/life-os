"""Assemble sections into prompt strings.

build_wake() — full wake snapshot, used by `steward wake` CLI and daemon spawns.
build_chat_prompt() — wake content for chat --append-system-prompt (no shell-out).
"""

from . import sections

# Order = priority. Identity-ish first, ambient state last.
WAKE_ORDER = [
    sections.render_header,
    sections.render_steward_tasks,
    sections.render_feedback,
    sections.render_last_session,
    sections.render_contracts,
    sections.render_observations,
    sections.render_dates,
    sections.render_contacts,
    sections.render_improvements,
    sections.render_mood,
    sections.render_commits,
    sections.render_comms,
    sections.render_telegram,
    sections.render_inbox,
    sections.render_xmit,
]


def build_wake() -> str:
    """Compose all wake sections into a single string."""
    parts: list[str] = []
    for renderer in WAKE_ORDER:
        try:
            text = renderer()
        except Exception:
            text = ""
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def build_chat_prompt() -> str:
    """Wake snapshot wrapped for system-prompt injection."""
    wake = build_wake()
    return f"<wake>\n{wake}\n</wake>" if wake else ""

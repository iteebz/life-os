"""Assemble sections into prompt strings.

build_wake() — full wake snapshot, used by `steward wake` CLI and daemon spawns.
build_chat_prompt() — wake + constitution for chat --append-system-prompt.
"""

from pathlib import Path

from . import sections

LIFE_DIR = Path.home() / "life"
STEWARD_DIR = LIFE_DIR / "steward"

CONSTITUTION = [
    ("life", LIFE_DIR / "LIFE.md"),
    ("memory", STEWARD_DIR / "memory.md"),
    ("human", STEWARD_DIR / "human.md"),
]

# Order = priority. Identity-ish first, ambient state last.
WAKE_ORDER = [
    sections.render_header,
    sections.render_handover,
    sections.render_steward_tasks,
    sections.render_feedback,
    sections.render_last_session,
    sections.render_contracts,
    sections.render_observations,
    sections.render_dates,
    sections.render_improvements,
    sections.render_skills,
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
    """Wake snapshot + constitution markdowns for system-prompt injection."""
    parts: list[str] = []
    for tag, path in CONSTITUTION:
        if path.exists():
            text = path.read_text().strip()
            if text:
                parts.append(f"<{tag}>\n{text}\n</{tag}>")
    wake = build_wake()
    if wake:
        parts.append(f"<wake>\n{wake}\n</wake>")
    return "\n\n".join(parts)

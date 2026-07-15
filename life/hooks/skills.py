"""Keyword-triggered skill injection — fires on UserPromptSubmit, no `life skill <name>` needed."""

import contextlib
import re
from pathlib import Path

from life.hooks import signals
from lifeos.core.comms import events
from lifeos.core.lib.frontmatter import field

_SKILLS_DIR = Path.home() / "life" / "steward" / "skills"


def _parse_keywords(raw: str | None) -> list[str]:
    if not raw:
        return []
    raw = raw.strip().strip("[]")
    return [w.strip().lower() for w in raw.split(",") if w.strip()]


def inject_matching_skills(prompt: str, session_id: str) -> list[str]:
    """Return skill bodies whose keywords match the prompt, deduped per session."""
    if not _SKILLS_DIR.is_dir():
        return []

    tokens = set(re.findall(r"[a-z0-9']+", prompt.lower()))
    if not tokens:
        return []

    state = signals.load_state()
    injected: list[str] = []

    for path in sorted(_SKILLS_DIR.glob("*.md")):
        text = path.read_text()
        keywords = _parse_keywords(field(text, "keywords"))
        if not keywords or not tokens & set(keywords):
            continue
        flag = f"skill_injected_{path.stem}_{session_id[:8]}"
        if state.get(flag):
            continue
        state[flag] = "1"
        injected.append(f"[skill: {path.stem}]\n{text}\n[/skill]")
        with contextlib.suppress(Exception):
            events.record("skill.loaded", payload={"name": path.stem, "source": "keyword"})

    if injected:
        signals.save_state(state)
    return injected

"""Assemble sections into prompt strings.

build_wake() — full wake snapshot, used by `steward wake` CLI and daemon sessions.
build_chat_prompt() — fragments + constitution + wake for chat --append-system-prompt.
render() — named (name, content) pairs → XML blocks.
"""

from pathlib import Path

from . import sections

LIFE_DIR = Path.home() / "life"
STEWARD_DIR = LIFE_DIR / "steward"
CTX_DIR = LIFE_DIR / "life-os" / "ctx"

CONSTITUTION = [
    ("geometry", STEWARD_DIR / "geometry.md"),
    ("life", LIFE_DIR / "LIFE.md"),
    ("memory", STEWARD_DIR / "memory.md"),
    ("human", STEWARD_DIR / "human.md"),
]

# Order = priority. Identity-ish first, ambient state last.
WAKE_ORDER = [
    sections.render_header,
    sections.render_shipped_today,
    sections.render_steward_tasks,
    sections.render_trails,
    sections.render_today,
    sections.render_milestones,
    sections.render_feedback,
    sections.render_observatory,
    sections.render_last_session,
    sections.render_contracts,
    sections.render_patterns,
    sections.render_observations,
    sections.render_dates,
    sections.render_skills,
    sections.render_mood,
    sections.render_commits,
    sections.render_comms,
    sections.render_telegram,
    sections.render_inbox,
    sections.render_space_mail,
]


def render(frags: list[tuple[str, str]], sep: str = "\n\n") -> str:
    """Render named (name, content) pairs into XML blocks."""
    return sep.join(f"<{name}>\n{content}\n</{name}>" for name, content in frags)


def load_manifest(mode: str) -> list[tuple[str, str]]:
    """Load fragments listed in ctx/{mode}.md. Returns (name, content) pairs."""
    manifest = CTX_DIR / f"{mode}.md"
    if not manifest.exists():
        return []
    names = [n.strip() for n in manifest.read_text().splitlines() if n.strip()]
    frags = []
    for name in names:
        path = CTX_DIR / "fragments" / f"{name}.md"
        if path.exists():
            frags.append((name, path.read_text().strip()))
    return frags


_WAKE_BUDGET = 28_000  # chars — stay well under 100k context


def build_wake() -> str:
    """Compose wake sections up to budget. WAKE_ORDER is priority order — drop from the tail.

    Each section is wrapped in its own <name> tag (name = renderer without the
    render_ prefix, matching `life steward inspect`) so the model can reference
    subparts and per-section content can be diffed across refs.
    """
    parts: list[str] = []
    total = 0
    for renderer in WAKE_ORDER:
        try:
            text = renderer()
        except Exception:
            text = ""
        if not text:
            continue
        if total + len(text) > _WAKE_BUDGET:
            parts.append(f"[wake truncated at {total} chars — {_WAKE_BUDGET} budget]")
            break
        name = renderer.__name__.removeprefix("render_")
        parts.append(f"<{name}>\n{text}\n</{name}>")
        total += len(text)
    return "\n\n".join(parts)


def build_chat_prompt() -> str:
    """Fragments + constitution markdowns + wake for system-prompt injection."""
    parts: list[str] = []
    frags = load_manifest("chat")
    if frags:
        parts.append(render(frags))
    for tag, path in CONSTITUTION:
        if path.exists():
            text = path.read_text().strip()
            if text:
                parts.append(f"<{tag}>\n{text}\n</{tag}>")
    wake = build_wake()
    if wake:
        parts.append(f"<wake>\n{wake}\n</wake>")
    return "\n\n".join(parts)

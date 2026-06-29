"""Skills — markdown playbooks loadable on demand.

Files in ~/life/steward/skills/<name>.md. Optional frontmatter `when:` one-liner
indexed in wake; body fetched via `life skill <name>`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fncli import cli

from lifeos.core.errors import NotFoundError
from lifeos.core.lib.frontmatter import _RE as _FM_RE
from lifeos.core.lib.frontmatter import field

SKILLS_DIR = Path.home() / "life" / "steward" / "skills"


@dataclass(frozen=True)
class Skill:
    name: str
    when: str
    body: str


def _parse(path: Path) -> Skill:
    text = path.read_text()
    when = (field(text, "when") or "")[:128]
    m = _FM_RE.match(text)
    body = text[m.end() :].lstrip() if m else text
    return Skill(name=path.stem, when=when, body=body.rstrip())


def list_skills() -> list[Skill]:
    if not SKILLS_DIR.exists():
        return []
    return sorted(
        (_parse(p) for p in SKILLS_DIR.glob("*.md") if p.stem.lower() != "readme"),
        key=lambda s: s.name,
    )


def get_skill(name: str) -> Skill:
    path = SKILLS_DIR / f"{name}.md"
    if not path.exists():
        raise NotFoundError(f"no skill '{name}' — try `life skill`")
    return _parse(path)


@cli("life", flags={"name": []})
def skill(name: str | None = None):
    """Show a skill, or list available skills"""
    if not name:
        skills = list_skills()
        if not skills:
            print("no skills — drop markdown into ~/life/steward/skills/")
            return
        width = max(len(s.name) for s in skills)
        for s in skills:
            when = f"  {s.when}" if s.when else ""
            print(f"  {s.name:<{width}}{when}")
        return
    s = get_skill(name)
    print(s.body)

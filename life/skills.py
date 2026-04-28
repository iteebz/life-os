"""Skills — markdown playbooks loadable on demand.

Files in ~/life/steward/skills/<name>.md. Optional frontmatter `when:` one-liner
indexed in wake; body fetched via `life skill <name>`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fncli import cli

from life.core.errors import NotFoundError

SKILLS_DIR = Path.home() / "life" / "steward" / "skills"


@dataclass(frozen=True)
class Skill:
    name: str
    when: str
    body: str


def _parse(path: Path) -> Skill:
    text = path.read_text()
    when = ""
    body = text
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            front = text[4:end]
            body = text[end + 5 :].lstrip()
            for line in front.splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    if k.strip() == "when":
                        when = v.strip()
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

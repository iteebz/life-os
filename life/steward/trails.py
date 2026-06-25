"""Trails — breadcrumbs for self. Lines of inquiry that survive context death."""

import re
from pathlib import Path

from fncli import cli

from life.lib import ansi
from life.lib import frontmatter as fm

_DIR = Path.home() / "life" / "notes" / "steward" / "trails"
_FM_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)
_CAP = 10


def _first_paragraph(text: str) -> str | None:
    body = _FM_RE.sub("", text, count=1)
    para: list[str] = []
    for line in body.splitlines():
        if line.startswith("#"):
            continue
        if line.strip():
            para.append(line.strip())
        elif para:
            break
    return " ".join(para) if para else None


def _parse(path: Path) -> tuple[str, str | None]:
    text = path.read_text()
    title = fm.title(path)
    desc = fm.field(text, "description") or _first_paragraph(text)
    return title, desc


def _files() -> list[Path]:
    if not _DIR.exists():
        return []
    return sorted(f for f in _DIR.glob("*.md") if f.name != "README.md")


def trail_index() -> list[tuple[str, str, str | None]]:
    """Return (slug, title, description) for all trail files."""
    return [(f.stem, *_parse(f)) for f in _files()]


@cli("life")
@cli("life steward")
def trails() -> None:
    """List active trails from steward/trails/"""
    files = _files()
    if not files:
        print("no trails")
        return
    for f in files:
        title, desc = _parse(f)
        suffix = f"  —  {desc}" if desc else ""
        print(f"  {title}{suffix}")
    if len(files) >= _CAP:
        print(ansi.red(f"\n  at cap ({_CAP}). close one before opening another."))


@cli("life steward trails")
def new(name: str) -> None:
    """Scaffold a new trail file"""
    if not _DIR.exists():
        _DIR.mkdir(parents=True)
    slug = name.lower().replace(" ", "-")
    path = _DIR / f"{slug}.md"
    if path.exists():
        print(ansi.red(f"already exists: {path.name}"))
        return
    files = _files()
    if len(files) >= _CAP:
        print(ansi.red(f"at cap ({_CAP} trails). graduate or delete one first."))
        return
    path.write_text(f"---\ndescription: \n---\n\n# {name}\n\n")
    print(ansi.green(f"created: {path.name}"))

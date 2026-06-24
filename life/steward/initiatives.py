from pathlib import Path

from fncli import cli

from life.lib import ansi
from life.lib import frontmatter as fm

_DIR = Path.home() / "life" / "steward" / "initiatives"


def _parse(path: Path) -> tuple[str, str | None]:
    text = path.read_text()
    status = fm.field(text, "status")
    title = fm.title(path)
    return title, status


def _files() -> list[Path]:
    if not _DIR.exists():
        return []
    return sorted(f for f in _DIR.glob("*.md") if f.name not in ("README.md", "SPRINT.md"))


def initiative_index() -> list[tuple[str, str, str]]:
    """Return (slug, status, title) for all initiative files."""
    results = []
    for f in _files():
        title, status = _parse(f)
        results.append((f.stem, status or "?", title))
    return results


@cli("life")
@cli("life steward")
def initiatives() -> None:
    """List initiatives from steward/initiatives/"""
    if not _DIR.exists():
        print("no initiatives folder found")
        return
    files = sorted(f for f in _DIR.glob("*.md") if f.name not in ("README.md", "SPRINT.md"))
    if not files:
        print("no initiatives")
        return
    open_items = []
    closed_items = []
    invalid = []
    for f in files:
        title, status = _parse(f)
        if status is None:
            invalid.append((f.name, title))
        elif status in ("closed", "done"):
            closed_items.append((title, status))
        else:
            open_items.append((title, status))
    if invalid:
        print(ansi.red(f"  missing status field ({len(invalid)})\n"))
        for fname, title in invalid:
            print(f"  {ansi.red('!')}  {fname}  —  {title}")
        print()
    if open_items:
        print(ansi.muted(f"  open ({len(open_items)})\n"))
        for title, status in open_items:
            print(f"  {ansi.muted(f'[{status}]'):<24}  {title}")
    if closed_items:
        print(ansi.muted(f"\n  closed ({len(closed_items)})\n"))
        for title, _ in closed_items:
            print(f"  {ansi.muted('[done]'):<24}  {ansi.muted(title)}")


@cli("life steward initiatives")
def new(name: str) -> None:
    """Scaffold a new initiative file with required frontmatter"""
    slug = name.lower().replace(" ", "-")
    path = _DIR / f"{slug}.md"
    if path.exists():
        print(ansi.red(f"already exists: {path.name}"))
        return
    path.write_text(f"---\nstatus: idea\n---\n\n# {name}\n\n")
    print(ansi.green(f"created: {path.name}"))

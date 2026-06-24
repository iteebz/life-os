from pathlib import Path

from fncli import cli

from life.lib import ansi
from life.lib import frontmatter as fm

_DIR = Path.home() / "life" / "steward" / "patterns"


def _parse(path: Path) -> tuple[str, str, str]:
    text = path.read_text()
    status = fm.field(text, "status") or "active"
    scope = fm.field(text, "scope") or ""
    title = fm.title(path)
    return title, status, scope


@cli("life")
@cli("life steward")
def patterns() -> None:
    """List patterns from steward/patterns/"""
    if not _DIR.exists():
        print("no patterns folder found")
        return
    files = sorted(f for f in _DIR.glob("*.md") if f.name != "README.md")
    if not files:
        print("no patterns")
        return
    active, graduated = [], []
    for f in files:
        title, status, scope = _parse(f)
        if status == "graduated":
            graduated.append((title, scope))
        else:
            active.append((title, status, scope))
    if active:
        print(ansi.muted(f"  active ({len(active)})\n"))
        for title, status, scope in active:
            suffix = ansi.muted(f"  {scope}") if scope else ""
            print(f"  {ansi.muted(f'[{status}]'):<24}  {title}{suffix}")
    if graduated:
        print(ansi.muted(f"\n  graduated ({len(graduated)})\n"))
        for title, _scope in graduated:
            print(f"  {ansi.muted('[graduated]'):<24}  {ansi.muted(title)}")

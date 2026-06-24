from pathlib import Path

from fncli import cli

from life.lib import ansi
from life.lib import frontmatter as fm

_DIR = Path.home() / "life" / "steward" / "initiatives"


def _parse(path: Path) -> tuple[str, str]:
    text = path.read_text()
    status = fm.field(text, "status") or "open"
    title = fm.title(path)
    return title, status


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
    for f in files:
        title, status = _parse(f)
        if status in ("closed", "done"):
            closed_items.append((title, status))
        else:
            open_items.append((title, status))
    if open_items:
        print(ansi.muted(f"  open ({len(open_items)})\n"))
        for title, status in open_items:
            print(f"  {ansi.muted(f'[{status}]'):<24}  {title}")
    if closed_items:
        print(ansi.muted(f"\n  closed ({len(closed_items)})\n"))
        for title, _ in closed_items:
            print(f"  {ansi.muted('[done]'):<24}  {ansi.muted(title)}")

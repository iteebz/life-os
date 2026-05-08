from pathlib import Path

from fncli import cli

from life.lib import ansi

_INITIATIVES_DIR = Path.home() / "life" / "steward" / "initiatives"


def _parse(path: Path) -> tuple[str, str]:
    """Return (title, status) from a markdown initiative file."""
    title = path.stem.replace("-", " ")
    status = "open"
    for line in path.read_text().splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
        if line.startswith("## status") or line.strip().lower() == "## status":
            continue
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        if line.strip().lower() == "## status":
            if i + 1 < len(lines):
                val = lines[i + 1].strip().lower().split()[0] if lines[i + 1].strip() else ""
                if val:
                    status = val
            break
    return title, status


@cli("life steward")
def initiatives() -> None:
    """List initiatives from steward/initiatives/"""
    if not _INITIATIVES_DIR.exists():
        print("no initiatives folder found")
        return
    files = sorted(f for f in _INITIATIVES_DIR.glob("*.md") if f.name != "README.md")
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
            tag = ansi.muted(f"[{status}]")
            print(f"  {tag}  {title}")
    if closed_items:
        print(ansi.muted(f"\n  closed ({len(closed_items)})\n"))
        for title, _ in closed_items:
            print(f"  {ansi.muted('[done]')}  {ansi.muted(title)}")

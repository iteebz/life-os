"""prompt inspection — see what loads into the steward system prompt.

`life prompt show [name]` — print full prompt, or one fragment/constitution doc
`life prompt size [mode]` — char/token breakdown per piece
`life prompt fragments` — list fragments + which manifests load each
"""

from __future__ import annotations

from pathlib import Path

from fncli import cli

from .assemble import CONSTITUTION, CTX_DIR, build_chat_prompt, build_wake, load_manifest

_MODES = ("chat", "auto", "tg")


def _frag_path(name: str) -> Path:
    return CTX_DIR / "fragments" / f"{name}.md"


def _all_fragments() -> list[str]:
    d = CTX_DIR / "fragments"
    return sorted(p.stem for p in d.glob("*.md")) if d.exists() else []


def _manifest_names(mode: str) -> list[str]:
    p = CTX_DIR / f"{mode}.md"
    if not p.exists():
        return []
    return [n.strip() for n in p.read_text().splitlines() if n.strip()]


@cli("life prompt")
def show(name: str | None = None):
    """Print full assembled chat prompt, or a single fragment/constitution doc."""
    if name is None:
        print(build_chat_prompt())
        return
    fp = _frag_path(name)
    if fp.exists():
        print(fp.read_text())
        return
    for tag, path in CONSTITUTION:
        if tag == name and path.exists():
            print(path.read_text())
            return
    if name == "wake":
        print(build_wake())
        return
    print(f"unknown: {name}. try `life prompt fragments` or one of: {', '.join(t for t, _ in CONSTITUTION)}, wake")


@cli("life prompt")
def size(mode: str = "chat"):
    """Char breakdown of every piece loaded into the prompt for a mode."""
    if mode not in _MODES:
        print(f"mode must be one of {_MODES}")
        return

    rows: list[tuple[str, str, int]] = []
    for name, content in load_manifest(mode):
        rows.append(("fragment", name, len(content)))
    if mode == "chat":
        for tag, path in CONSTITUTION:
            if path.exists():
                rows.append(("constitution", tag, len(path.read_text().strip())))
        rows.append(("wake", "wake", len(build_wake())))

    if not rows:
        print(f"nothing loads for mode={mode}")
        return

    width = max(len(r[1]) for r in rows)
    total = sum(r[2] for r in rows)
    print(f"{'kind':<13} {'name':<{width}}  chars   ~tok    %")
    print("-" * (13 + 1 + width + 22))
    for kind, name, n in sorted(rows, key=lambda r: -r[2]):
        pct = 100 * n / total if total else 0
        print(f"{kind:<13} {name:<{width}}  {n:>5}  {n // 4:>5}  {pct:>4.1f}")
    print("-" * (13 + 1 + width + 22))
    print(f"{'TOTAL':<13} {'':<{width}}  {total:>5}  {total // 4:>5}")


@cli("life prompt")
def fragments():
    """List all fragments and which mode manifests load each."""
    frags = _all_fragments()
    if not frags:
        print("no fragments found")
        return
    membership = {m: set(_manifest_names(m)) for m in _MODES}
    width = max(len(f) for f in frags)
    print(f"{'fragment':<{width}}  chat  auto  tg   chars")
    print("-" * (width + 26))
    for f in frags:
        path = _frag_path(f)
        n = len(path.read_text().strip()) if path.exists() else 0
        marks = [" ✓ " if f in membership[m] else " · " for m in _MODES]
        print(f"{f:<{width}}  {marks[0]}  {marks[1]}  {marks[2]}  {n:>5}")

    print()
    orphans = [f for f in frags if not any(f in membership[m] for m in _MODES)]
    if orphans:
        print(f"orphans (no manifest references): {', '.join(orphans)}")
    for m in _MODES:
        missing = [n for n in _manifest_names(m) if not _frag_path(n).exists()]
        if missing:
            print(f"{m} manifest references missing fragment(s): {', '.join(missing)}")

"""Inspect assembled wake prompt — per-section sizes, budget breakdown."""

from __future__ import annotations

import sys

import fncli
from fncli import cli

from life.ctx.assemble import CONSTITUTION, WAKE_ORDER
from lifeos.core.store.migrations import init

BUDGET_CHARS = 100_000


def _bar(pct: float, width: int = 20) -> str:
    filled = min(width, int(pct / 100 * width))
    return "█" * filled + "░" * (width - filled)


@cli("life steward")
def inspect(full: bool = False) -> None:
    """Show wake assembly: per-section char counts vs budget. --full dumps content."""
    init()

    rows: list[tuple[str, int, str]] = []

    for tag, path in CONSTITUTION:
        text = path.read_text().strip() if path.exists() else ""
        rows.append((f"const:{tag}", len(text), text))

    for renderer in WAKE_ORDER:
        try:
            text = renderer() or ""
        except Exception as e:
            text = f"<error: {e}>"
        rows.append((renderer.__name__.removeprefix("render_"), len(text), text))

    total = sum(n for _, n, _ in rows)
    pct_total = total / BUDGET_CHARS * 100

    name_w = max(len(name) for name, _, _ in rows)
    print(f"{'section':<{name_w}}  {'chars':>7}  {'%':>5}  bar")
    print("-" * (name_w + 40))
    for name, n, _ in rows:
        pct = n / BUDGET_CHARS * 100
        marker = "·" if n == 0 else " "
        print(f"{name:<{name_w}}  {n:>7,}  {pct:>4.1f}% {marker}{_bar(pct, 16)}")
    print("-" * (name_w + 40))
    print(f"{'TOTAL':<{name_w}}  {total:>7,}  {pct_total:>4.1f}%  {_bar(pct_total)}  / {BUDGET_CHARS:,}")

    if full:
        print()
        for name, n, text in rows:
            if not text:
                continue
            print(f"\n=== {name} ({n:,} chars) ===")
            print(text)


def main() -> None:
    init()
    sys.exit(fncli.dispatch(["life", "steward", "inspect", *sys.argv[1:]]))

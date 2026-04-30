"""Seed ~/life with the steward CLAUDE.md. Idempotent."""

from __future__ import annotations

from pathlib import Path

from fncli import cli

from life.core.config import Config, get_partner_tag, get_user_name

LIFE_HOME = Path.home() / "life"
TEMPLATE = Path(__file__).parent / "ctx" / "seed" / "CLAUDE.md"


@cli("life", flags={"force": ["-f", "--force"]})
def init(force: bool = False):
    """Seed ~/life/CLAUDE.md with the steward mandate"""
    LIFE_HOME.mkdir(parents=True, exist_ok=True)
    target = LIFE_HOME / "CLAUDE.md"

    if target.exists() and not force:
        print(f"already initialized: {target}")
    else:
        target.write_text(TEMPLATE.read_text())
        print(f"{'overwrote' if force else 'created'}: {target}")

    print(f"  user_name:   {get_user_name()}")
    print(f"  partner_tag: {get_partner_tag() or '(unset)'}")
    print("set with: life config user_name <name> / life config partner_tag <tag>")


@cli("life", flags={"key": [], "value": []})
def config(key: str | None = None, value: str | None = None):
    """Get or set config values (user_name, partner_tag, profile)"""
    cfg = Config()
    if key is None:
        for k in ("user_name", "partner_tag", "profile"):
            v = cfg.get(k)
            print(f"  {k}: {v if v else '(unset)'}")
        return
    if value is None:
        v = cfg.get(key)
        print(v if v else "(unset)")
        return
    cfg.set(key, value)
    print(f"set {key} = {value}")

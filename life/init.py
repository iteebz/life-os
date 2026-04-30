"""Seed ~/life with steward scaffold. Idempotent."""

from __future__ import annotations

import subprocess
from pathlib import Path

from fncli import cli

from life.core.config import Config, get_partner_tag, get_user_name

LIFE_HOME = Path.home() / "life"
SEED_DIR = Path(__file__).parent / "ctx" / "seed"


def _render(text: str, user: str, partner: str) -> str:
    return (
        text.replace("{User}", user.capitalize())
        .replace("{user}", user)
        .replace("{Partner}", partner.capitalize())
        .replace("{partner}", partner)
    )


def _setup_git(github_url: str | None) -> None:
    git_dir = LIFE_HOME / ".git"
    if not git_dir.exists():
        subprocess.run(["git", "init"], cwd=LIFE_HOME, check=True, capture_output=True)
        print("  git init")

    if github_url:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=LIFE_HOME,
            capture_output=True,
        )
        if result.returncode == 0:
            subprocess.run(
                ["git", "remote", "set-url", "origin", github_url],
                cwd=LIFE_HOME,
                check=True,
                capture_output=True,
            )
            print(f"  remote updated: {github_url}")
        else:
            subprocess.run(
                ["git", "remote", "add", "origin", github_url],
                cwd=LIFE_HOME,
                check=True,
                capture_output=True,
            )
            print(f"  remote added: {github_url}")


@cli("life", flags={"force": ["-f", "--force"], "github": ["--github"]})
def init(force: bool = False, github: str | None = None):
    """Seed ~/life with steward scaffold (CLAUDE.md, LIFE.md, steward/, .gitignore)"""
    LIFE_HOME.mkdir(parents=True, exist_ok=True)

    user = get_user_name()
    partner = get_partner_tag() or "partner"

    # seed files: (src relative to SEED_DIR, dst relative to LIFE_HOME, force-overwrite)
    seed_files = [
        ("CLAUDE.md", True),
        ("LIFE.md", False),
        (".gitignore", False),
        ("steward/memory.md", False),
        ("steward/human.md", False),
    ]

    for rel, overwritable in seed_files:
        src = SEED_DIR / rel
        dst = LIFE_HOME / rel
        should_write = (force and overwritable) or not dst.exists()
        if should_write:
            dst.parent.mkdir(parents=True, exist_ok=True)
            content = _render(src.read_text(), user, partner)
            verb = "overwrote" if dst.exists() else "created"
            dst.write_text(content)
            print(f"  {verb}: {rel}")
        else:
            print(f"  exists:  {rel}")

    # steward/{user}/ placeholder
    user_dir = LIFE_HOME / "steward" / user
    user_dir.mkdir(parents=True, exist_ok=True)

    _setup_git(github)

    print()
    print(f"  user_name:   {user}")
    print(f"  partner_tag: {partner}")
    print("set with: life config user_name <name> / life config partner_tag <tag>")


@cli("life", flags={"key": [], "value": []})
def config(key: str | None = None, value: str | None = None):
    """Get or set config values (user_name, partner_tag, profile)"""
    cfg = Config()
    if key is None:
        for k in ("user_name", "partner_tag", "profile"):
            v = cfg.get(k)
            print(f"  {k}: {v or '(unset)'}")
        return
    if value is None:
        v = cfg.get(key)
        print(v or "(unset)")
        return
    cfg.set(key, value)
    print(f"set {key} = {value}")

"""Git push across ~/life and its subrepos."""

import subprocess
from pathlib import Path


def push_repos() -> None:
    life_dir = Path.home() / "life"
    repos = [life_dir] + [d for d in life_dir.iterdir() if d.is_dir() and (d / ".git").exists()]
    for repo in repos:
        result = subprocess.run(
            ["git", "push"],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        name = repo.name if repo != life_dir else "life"
        if result.returncode == 0:
            print(f"  pushed {name}")
        else:
            msg = (
                (result.stderr or result.stdout).strip().splitlines()[0]
                if (result.stderr or result.stdout)
                else "no remote?"
            )
            print(f"  {name}: {msg}")

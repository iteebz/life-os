"""life install — reinstall life-cli editable and regenerate spawn hooks.

Idempotent. Run after pulling, after refactors, when settings.local.json
goes stale, or whenever spawn hooks point at dead paths.
"""

import subprocess
from pathlib import Path

from fncli import cli

LIFE_OS = Path.home() / "life" / "life-os"


@cli("life")
def install():
    """Reinstall life-cli editable and refresh chat hook config"""
    print(f"→ uv tool install --reinstall --force --editable {LIFE_OS}")
    rc = subprocess.run(
        ["uv", "tool", "install", "--reinstall", "--force", "--editable", str(LIFE_OS)],
    ).returncode
    if rc != 0:
        print(f"install failed (rc={rc})")
        return rc

    from life.steward.chat import _ensure_hooks_config
    _ensure_hooks_config()
    print("→ hooks refreshed in ~/life/.claude/settings.local.json")
    return 0

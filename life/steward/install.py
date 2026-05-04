"""steward install — sync life-os/scripts/ to ~/.local/bin/."""

import shutil
from pathlib import Path

from fncli import cli

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
BIN_DIR = Path.home() / ".local/bin"


@cli("life steward")
def install():
    """Copy all life-os scripts to ~/.local/bin (idempotent)."""
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    for src in sorted(SCRIPTS_DIR.iterdir()):
        if src.suffix == ".plist" or not src.is_file():
            continue
        dst = BIN_DIR / src.name
        shutil.copy2(src, dst)
        dst.chmod(0o755)
        print(f"  {src.name} → {dst}")

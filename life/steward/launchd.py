import subprocess
import sys
from pathlib import Path
from typing import Any

from fncli import cli

from ..lib.errors import echo, exit_error

PLIST_NAME = "com.life.steward.daemon.plist"
LAUNCHD_DIR = Path.home() / "Library/LaunchAgents"
PLIST_PATH = LAUNCHD_DIR / PLIST_NAME
LOG_DIR = Path.home() / ".life/steward"


def _get_life_path() -> str:
    result = subprocess.run(["which", "life"], capture_output=True, text=True)
    if result.returncode == 0:
        return result.stdout.strip()
    return str(Path(sys.executable).parent / "life")


def _generate_plist(interval: int = 10) -> str:
    life_path = _get_life_path()
    python_path = Path(sys.executable).parent

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.life.steward.daemon</string>
    <key>ProgramArguments</key>
    <array>
        <string>{life_path}</string>
        <string>steward</string>
        <string>daemon</string>
        <string>daemon-start</string>
        <string>--foreground</string>
        <string>--interval</string>
        <string>{interval}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{LOG_DIR}/launchd.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>{LOG_DIR}/launchd.stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>{python_path}:/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
        <key>HOME</key>
        <string>{Path.home()}</string>
    </dict>
</dict>
</plist>
"""


def install(interval: int = 10) -> tuple[bool, str]:
    LAUNCHD_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    plist_content = _generate_plist(interval)
    PLIST_PATH.write_text(plist_content)

    result = subprocess.run(
        ["launchctl", "load", str(PLIST_PATH)],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return False, result.stderr or "failed to load plist"

    return True, f"installed and loaded {PLIST_PATH}"


def uninstall() -> tuple[bool, str]:
    if not PLIST_PATH.exists():
        return False, "not installed"

    subprocess.run(
        ["launchctl", "unload", str(PLIST_PATH)],
        capture_output=True,
        text=True,
    )

    PLIST_PATH.unlink(missing_ok=True)
    return True, "uninstalled"


def launchd_status() -> dict[str, Any]:
    installed = PLIST_PATH.exists()

    running = False
    if installed:
        result = subprocess.run(
            ["launchctl", "list", "com.life.steward.daemon"],
            capture_output=True,
            text=True,
        )
        running = result.returncode == 0

    return {
        "installed": installed,
        "running": running,
        "plist_path": str(PLIST_PATH) if installed else None,
    }


@cli("life steward daemon", name="install")
def daemon_install(interval: int = 10) -> None:
    """Install steward daemon as launchd service (auto-start on boot)"""
    ok, msg = install(interval=interval)
    echo(msg)
    if not ok:
        exit_error("")


@cli("life steward daemon", name="uninstall")
def daemon_uninstall() -> None:
    """Uninstall steward daemon launchd service"""
    ok, msg = uninstall()
    echo(msg)
    if not ok:
        exit_error("")

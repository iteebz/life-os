import subprocess
from pathlib import Path

_DAEMON_LABEL = "com.life-os.daemon"
_PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{_DAEMON_LABEL}.plist"


def install_daemon() -> bool:
    venv_life = Path.home() / "life" / "life-os" / ".venv" / "bin" / "life"
    log_file = Path.home() / ".life" / "daemon.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{_DAEMON_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{venv_life}</string>
        <string>daemon</string>
        <string>start</string>
        <string>--foreground</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{log_file}</string>
    <key>StandardErrorPath</key>
    <string>{log_file}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key>
        <string>{Path.home()}</string>
        <key>PATH</key>
        <string>{venv_life.parent}:/opt/homebrew/bin:/opt/homebrew/opt/libpq/bin:{Path.home()}/.local/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
    <key>WorkingDirectory</key>
    <string>{Path.home()}/life/life-os</string>
</dict>
</plist>
"""

    current = _PLIST_PATH.read_text() if _PLIST_PATH.exists() else None
    if current == plist:
        result = subprocess.run(["launchctl", "list", _DAEMON_LABEL], capture_output=True)
        if result.returncode == 0:
            return False

    _PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PLIST_PATH.write_text(plist)

    subprocess.run(["launchctl", "unload", str(_PLIST_PATH)], capture_output=True)
    subprocess.run(["launchctl", "load", str(_PLIST_PATH)], capture_output=True)
    return True

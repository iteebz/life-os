"""life doctor — smoke-test the install. Diagnose drift between source and runtime.

Run after `uv tool install --reinstall --force --editable ~/life/life-os` or
whenever something feels off. Reports green/red per check; non-zero exit on failure.
"""

import json
import shutil
import subprocess
from pathlib import Path

from fncli import cli

LIFE_DIR = Path.home() / "life"
SETTINGS = LIFE_DIR / ".claude" / "settings.local.json"
PLIST = Path.home() / "Library" / "LaunchAgents" / "com.life.daemon.plist"
DB = Path.home() / ".life" / "life.db"
EXPECTED_BINS = ("life", "life-hook", "steward", "comms")


def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _fail(msg: str) -> None:
    print(f"  ✗ {msg}")


@cli("life")
def doctor() -> int:
    """Smoke-test install: binaries, hooks, daemon, db, dispatch"""
    failures = 0

    print("binaries:")
    for b in EXPECTED_BINS:
        path = shutil.which(b)
        if path:
            _ok(f"{b} → {path}")
        else:
            _fail(f"{b} missing on PATH")
            failures += 1

    print("\nlife-hook dispatch:")
    for event in ("tool", "prompt", "stop"):
        try:
            rc = subprocess.run(
                ["life-hook", event],
                input="{}",
                capture_output=True,
                text=True,
                timeout=10,
            ).returncode
            (_ok if rc == 0 else _fail)(f"life-hook {event} (rc={rc})")
            if rc != 0:
                failures += 1
        except Exception as e:
            _fail(f"life-hook {event}: {e}")
            failures += 1

    print("\nchat hook config:")
    if SETTINGS.exists():
        try:
            hooks = json.loads(SETTINGS.read_text()).get("hooks", {})
            for event in ("UserPromptSubmit", "Stop"):
                cmd = hooks.get(event, [{}])[0].get("hooks", [{}])[0].get("command", "")
                if not cmd:
                    _fail(f"{event} unset")
                    failures += 1
                    continue
                rc = subprocess.run(
                    cmd, shell=True, input="{}", capture_output=True, text=True, timeout=15
                ).returncode
                (_ok if rc == 0 else _fail)(f"{event}: {cmd} (rc={rc})")
                if rc != 0:
                    failures += 1
        except Exception as e:
            _fail(f"settings.local.json: {e}")
            failures += 1
    else:
        _fail(f"{SETTINGS} missing")
        failures += 1

    print("\ndaemon:")
    if PLIST.exists():
        _ok(f"plist installed → {PLIST}")
        result = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
        line = next((ln for ln in result.stdout.splitlines() if "com.life.daemon" in ln), None)
        if line:
            pid = line.split()[0]
            (_ok if pid != "-" else _fail)(f"daemon running (pid={pid})")
            if pid == "-":
                failures += 1
        else:
            _fail("daemon not loaded in launchctl")
            failures += 1
    else:
        _fail(f"plist missing at {PLIST}")
        failures += 1

    print("\ndb:")
    if DB.exists():
        _ok(f"db at {DB}")
    else:
        _fail(f"db missing at {DB}")
        failures += 1

    print()
    if failures:
        print(f"✗ {failures} check(s) failed")
        return 1
    print("✓ all green")
    return 0

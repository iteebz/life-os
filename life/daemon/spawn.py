"""Shared Claude spawning for daemon threads."""

import json
import shutil
import subprocess
from pathlib import Path

MAX_RESPONSE_LEN = 4000

_HOOK_SETTINGS = {
    "hooks": {
        "PreToolUse": [{"matcher": "", "hooks": [{"type": "command", "command": "life-hook tool"}]}],
    },
}


def _claude_bin() -> str:
    """Resolve the claude binary, checking nvm paths if not in PATH."""
    found = shutil.which("claude")
    if found:
        return found
    nvm_bin = Path.home() / ".nvm" / "versions" / "node"
    for node_ver in sorted(nvm_bin.glob("*/bin/claude"), reverse=True):
        return str(node_ver)
    raise FileNotFoundError("claude binary not found — ensure Claude Code CLI is installed")


def fetch_wake_context() -> str:
    """Run `life steward wake` and capture output for prompt injection."""
    try:
        result = subprocess.run(
            ["life", "steward", "wake"],
            cwd=Path.home() / "life",
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout.strip()
    except Exception as e:
        return f"(wake context unavailable: {e})"


def spawn_claude(prompt: str, timeout: int = 300, image_path: str | None = None) -> str:
    try:
        claude = _claude_bin()
    except FileNotFoundError as e:
        return f"[steward error: {e}]"

    cmd = [
        claude,
        "--print",
        "--no-session-persistence",
        "--dangerously-skip-permissions",
        "--model",
        "claude-sonnet-4-6",
        "--settings",
        json.dumps(_HOOK_SETTINGS),
    ]
    if image_path:
        cmd += ["--image", image_path]

    from life.lib.env import build_base_env

    env = build_base_env("tg")

    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            cwd=Path.home() / "life",
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout.strip()
        if not output and result.stderr:
            return f"[steward error: {result.stderr[:200]}]"
        if len(output) > MAX_RESPONSE_LEN:
            output = output[:MAX_RESPONSE_LEN] + "\n\n[truncated]"
        return output or "[steward: no response]"
    except subprocess.TimeoutExpired:
        return f"[steward: timed out ({timeout}s)]"
    except Exception as e:
        return f"[steward error: {e}]"

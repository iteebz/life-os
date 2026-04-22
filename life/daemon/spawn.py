"""Shared Claude spawning for daemon threads."""

import os
import subprocess
from pathlib import Path

MAX_RESPONSE_LEN = 4000


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


def spawn_claude(prompt: str, timeout: int = 120) -> str:
    cmd = [
        "claude",
        "--print",
        "--no-session-persistence",
        "--dangerously-skip-permissions",
        "--model",
        "claude-sonnet-4-6",
    ]
    env = os.environ.copy()
    env.pop("ANTHROPIC_BASE_URL", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)

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

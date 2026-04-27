"""Shared Claude spawning for daemon threads."""

import json
import shutil
import subprocess
from pathlib import Path

from life.lib.providers.claude import SPAWN_SETTINGS
from life.lib.providers.claude import build_env as build_claude_env

MAX_RESPONSE_LEN = 4000


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
    """Build wake snapshot for prompt injection (in-process, no subprocess)."""
    try:
        from life.ctx.assemble import build_wake  # noqa: PLC0415, I001 — cycle: ctx.sections→inbound→session→spawn→ctx.assemble
        return build_wake()
    except Exception as e:
        return f"(wake context unavailable: {e})"


def spawn_claude(
    prompt: str,
    timeout: int = 300,
    image_path: str | None = None,
    resume_session_id: str | None = None,
) -> str:
    try:
        claude = _claude_bin()
    except FileNotFoundError as e:
        return f"[steward error: {e}]"

    cmd = [
        claude,
        "--print",
        "--dangerously-skip-permissions",
        "--model",
        "claude-sonnet-4-6",
        "--settings",
        json.dumps(SPAWN_SETTINGS),
    ]
    if resume_session_id:
        cmd += ["--resume", resume_session_id]
    if image_path:
        cmd += ["--image", image_path]

    env = build_claude_env("tg")

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

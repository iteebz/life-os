"""Claude runner for daemon sessions."""

import json
import shutil
import subprocess
import uuid
from collections.abc import Callable
from pathlib import Path

from life.ctx.assemble import build_wake
from life.lib.env import Mode
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
        return build_wake()
    except Exception as e:
        return f"(wake context unavailable: {e})"


def run_claude(
    prompt: str,
    timeout: int = 600,
    image_path: str | None = None,
    resume_session_id: str | None = None,
    steward_session_id: str | None = None,
    on_pid: Callable[[int], None] | None = None,
    mode: Mode = "tg",
) -> str:
    """Spawn claude and return its output.

    on_pid: optional callback called with the process PID immediately after spawn,
    before waiting. Used by the daemon to register the session as hookable.
    mode: steward mode injected into env — 'tg' for telegram sessions, 'auto' for autonomous.
    """
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
        prompt = f"[image attached at {image_path} — use Read tool to view it]\n\n{prompt}"

    env = build_claude_env(mode)
    env["STEWARD_SESSION_ID"] = steward_session_id or resume_session_id or str(uuid.uuid4())

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=Path.home() / "life",
            env=env,
            text=True,
        )
        if on_pid is not None:
            on_pid(proc.pid)
        try:
            stdout, stderr = proc.communicate(input=prompt, timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return f"[steward: timed out ({timeout}s)]"
        output = stdout.strip()
        if not output and stderr:
            return f"[steward error: {stderr[:200]}]"
        if len(output) > MAX_RESPONSE_LEN:
            output = output[:MAX_RESPONSE_LEN] + "\n\n[truncated]"
        return output or "[steward: no response]"
    except Exception as e:
        return f"[steward error: {e}]"

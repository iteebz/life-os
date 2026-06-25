"""Steward environment accessors — the single source of truth for spawn context.

Mirrors space/infra/env.py. Every launch site sets these env vars;
runtime code reads them here.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

# The three steward spawn modes:
#   auto — autonomous daemon spawn (no human present)
#   chat — interactive CLI session (tyson is typing)
#   tg   — telegram daemon session (tyson may reply)
Mode = Literal["auto", "chat", "tg"]

MODES: frozenset[str] = frozenset({"auto", "chat", "tg"})


def mode() -> Mode | None:
    """Return current spawn mode, or None if not in a steward spawn."""
    val = os.environ.get("STEWARD_MODE")
    if val in MODES:
        return val  # type: ignore[return-value]
    return None


def session_id() -> str | None:
    """DB session id for the current spawn."""
    return os.environ.get("STEWARD_SESSION_ID")


def is_auto() -> bool:
    return mode() == "auto"


def is_chat() -> bool:
    return mode() == "chat"


def is_tg() -> bool:
    return mode() == "tg"


def is_interactive() -> bool:
    """True if a human might be reading in real time."""
    return mode() in ("chat", "tg")


# --- env builder (used by launch sites) ---

# Keys safe to inherit from host. Whitelist, not blacklist.
_SAFE_KEYS = frozenset(
    {
        "HOME",
        "PATH",
        "SHELL",
        "TERM",
        "LANG",
        "USER",
        "TMPDIR",
        "XDG_RUNTIME_DIR",
        # terminal capability vars — without these, Claude Code probes via escape
        # sequences and the terminal's response leaks a phantom keystroke ('p').
        "COLORTERM",
        "TERM_PROGRAM",
        "TERM_PROGRAM_VERSION",
        "LC_CTYPE",
        "LC_ALL",
        "ITERM_SESSION_ID",
        # life-os needs these
        "LIFE_DB",
        "LIFE_DIR",
        "STEWARD_SESSION_ID",
    }
)

# Keys that must never leak into sessions.
_BLOCKED_KEYS = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "AWS_SECRET_ACCESS_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
    }
)


_API_KEY_FILE = Path.home() / ".life" / "api_key"


def _read_api_key() -> str | None:
    """Read API key from file — no keychain, no password prompts, works over SSH."""
    if _API_KEY_FILE.exists():
        return _API_KEY_FILE.read_text().strip() or None
    return None


def build_base_env(spawn_mode: Mode) -> dict[str, str]:
    """Build a clean env dict for a steward spawn. Whitelist-only.

    Each launch site should call this, then layer on provider-specific
    and mode-specific vars (git identity, model keys, etc).
    """
    environ: dict[str, str] = {}

    for key in _SAFE_KEYS:
        if val := os.environ.get(key):
            environ[key] = val

    environ["STEWARD_MODE"] = spawn_mode

    if api_key := _read_api_key():
        environ["ANTHROPIC_API_KEY"] = api_key

    return environ

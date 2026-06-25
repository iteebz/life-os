"""Deprecated: use life.daemon.claude instead."""

from lifeos.steward.daemon.claude import fetch_wake_context, run_claude

spawn_claude = run_claude

__all__ = ["fetch_wake_context", "run_claude", "spawn_claude"]

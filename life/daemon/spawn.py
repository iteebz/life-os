"""Deprecated: use life.daemon.claude instead."""

from life.daemon.claude import fetch_wake_context, run_claude

spawn_claude = run_claude

__all__ = ["fetch_wake_context", "run_claude", "spawn_claude"]

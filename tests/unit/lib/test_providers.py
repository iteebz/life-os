"""Tests for claude provider env builder."""

from life.lib.providers.claude import build_env


def test_auto_env_disables_claude_features():
    env = build_env("auto")
    assert env["STEWARD_MODE"] == "auto"
    assert env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] == "1"
    assert env["CLAUDE_CODE_DISABLE_1M_CONTEXT"] == "1"


def test_chat_env_skips_spawn_flags():
    env = build_env("chat")
    assert env["STEWARD_MODE"] == "chat"
    assert "CLAUDE_CODE_DISABLE_AUTO_MEMORY" not in env
    assert "CLAUDE_CODE_DISABLE_1M_CONTEXT" not in env


def test_tg_env_skips_spawn_flags():
    env = build_env("tg")
    assert env["STEWARD_MODE"] == "tg"
    assert "CLAUDE_CODE_DISABLE_AUTO_MEMORY" not in env

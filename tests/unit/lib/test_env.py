"""Tests for steward env module — mirrors spacebrr's test_launch_env.py."""


from life.lib.env import build_base_env, is_auto, is_chat, is_interactive, is_tg, mode


def test_mode_reads_env(monkeypatch):
    monkeypatch.setenv("STEWARD_MODE", "auto")
    assert mode() == "auto"


def test_mode_returns_none_for_unknown(monkeypatch):
    monkeypatch.setenv("STEWARD_MODE", "bogus")
    assert mode() is None


def test_mode_returns_none_when_absent(monkeypatch):
    monkeypatch.delenv("STEWARD_MODE", raising=False)
    assert mode() is None


def test_is_helpers(monkeypatch):
    monkeypatch.setenv("STEWARD_MODE", "auto")
    assert is_auto()
    assert not is_chat()
    assert not is_tg()
    assert not is_interactive()

    monkeypatch.setenv("STEWARD_MODE", "chat")
    assert is_chat()
    assert is_interactive()

    monkeypatch.setenv("STEWARD_MODE", "tg")
    assert is_tg()
    assert is_interactive()


def test_build_base_env_sets_mode():
    env = build_base_env("auto")
    assert env["STEWARD_MODE"] == "auto"


def test_build_base_env_whitelists_keys(monkeypatch):
    monkeypatch.setenv("HOME", "/Users/test")
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "supersecret")

    env = build_base_env("chat")
    assert env["HOME"] == "/Users/test"
    assert env["PATH"] == "/usr/bin"
    assert "ANTHROPIC_API_KEY" not in env
    assert "AWS_SECRET_ACCESS_KEY" not in env


def test_build_base_env_does_not_leak_host_secrets(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-other")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok")
    env = build_base_env("auto")
    assert "OPENAI_API_KEY" not in env
    assert "ANTHROPIC_AUTH_TOKEN" not in env

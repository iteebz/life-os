"""Claude provider — env + command builders for steward spawns."""

from life.lib.env import Mode, build_base_env

_DEFAULT_MODEL = "claude-sonnet-4-6"

# Claude Code overrides — parity with spacebrr SPAWN_ENV_FLAGS.
# We own context, memory, and compaction. All modes get the full set.
_CLAUDE_FLAGS: dict[str, str] = {
    # context
    "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
    "CLAUDE_CODE_DISABLE_1M_CONTEXT": "1",
    "DISABLE_AUTO_COMPACT": "1",
    "DISABLE_CLAUDE_CODE_SM_COMPACT": "1",
    # quota
    "CLAUDE_CODE_ENABLE_PROMPT_SUGGESTION": "false",
    "ENABLE_PROMPT_CACHING_1H": "1",
    # privacy / telemetry
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    "DISABLE_ERROR_REPORTING": "1",
    "DISABLE_TELEMETRY": "1",
    # tooling
    "DISABLE_AUTOUPDATER": "1",
    "DISABLE_INSTALLATION_CHECKS": "1",
    "FORCE_UV_OFF": "1",
}


def build_env(spawn_mode: Mode) -> dict[str, str]:
    """Build a complete process env for a Claude steward spawn."""
    env = build_base_env(spawn_mode)
    env.update(_CLAUDE_FLAGS)
    return env


def build_command(prompt: str, model: str = _DEFAULT_MODEL) -> list[str]:
    return [
        "claude",
        "--print",
        "--output-format",
        "stream-json",
        "--verbose",
        "--dangerously-skip-permissions",
        "--model",
        model,
        prompt,
    ]

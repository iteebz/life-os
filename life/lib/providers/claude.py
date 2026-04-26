"""Claude provider — env + command builders for steward spawns."""

from life.lib.env import Mode, build_base_env

_DEFAULT_MODEL = "claude-sonnet-4-6"

# Claude-specific env flags for autonomous spawns.
_SPAWN_FLAGS: dict[str, str] = {
    "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
    "CLAUDE_CODE_DISABLE_1M_CONTEXT": "1",
}


def build_env(spawn_mode: Mode) -> dict[str, str]:
    """Build a complete process env for a Claude steward spawn."""
    env = build_base_env(spawn_mode)
    if spawn_mode == "auto":
        env.update(_SPAWN_FLAGS)
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

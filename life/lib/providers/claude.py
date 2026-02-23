import os

_DEFAULT_MODEL = "claude-sonnet-4-6"


def build_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("ANTHROPIC_BASE_URL", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
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

"""Claude provider — env flags and settings for steward sessions."""

from pathlib import Path

from lifeos.core.lib.env import Mode, build_base_env

# Claude Code overrides — parity with spacebrr SPAWN_ENV_FLAGS.
# We own context, memory, and compaction. All modes get the full set.
_CLAUDE_FLAGS: dict[str, str] = {
    # context — we own memory, compaction, and context window
    "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
    "CLAUDE_CODE_DISABLE_1M_CONTEXT": "1",
    "DISABLE_AUTO_COMPACT": "1",
    # quota — no speculative prefill, extended cache
    "CLAUDE_CODE_ENABLE_PROMPT_SUGGESTION": "false",
    "ENABLE_PROMPT_CACHING_1H": "1",
    # privacy — zero phoning home
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    "DISABLE_ERROR_REPORTING": "1",
    "DISABLE_TELEMETRY": "1",
    "CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY": "1",
    # bash — long-running steward ops (refactors, db ops) outlast 2min default
    "BASH_DEFAULT_TIMEOUT_MS": "600000",
    "BASH_MAX_TIMEOUT_MS": "1800000",
    # install — no self-mutation
    "DISABLE_AUTOUPDATER": "1",
    "DISABLE_INSTALLATION_CHECKS": "1",
    "DISABLE_UPGRADE_COMMAND": "1",
    "DISABLE_INSTALL_GITHUB_APP_COMMAND": "1",
}


SPAWN_SETTINGS: dict[str, object] = {
    "includeCoAuthoredBy": False,
    "includeGitInstructions": False,
    "promptSuggestionEnabled": False,
    "feedbackSurveyRate": 0,
    "spinnerTipsEnabled": False,
    "hooks": {
        "PreToolUse": [{"matcher": "", "hooks": [{"type": "command", "command": "life hook tool"}]}],
        "PostToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "life hook post-tool"}]}],
        "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "life hook prompt"}]}],
    },
}


def build_env(spawn_mode: Mode) -> dict[str, str]:
    """Build a complete process env for a Claude steward spawn."""
    env = build_base_env(spawn_mode)
    env.update(_CLAUDE_FLAGS)
    hooks_dir = Path.home() / ".life" / "hooks"
    if hooks_dir.is_dir():
        env["GIT_CONFIG_COUNT"] = "1"
        env["GIT_CONFIG_KEY_0"] = "core.hooksPath"
        env["GIT_CONFIG_VALUE_0"] = str(hooks_dir)
    return env

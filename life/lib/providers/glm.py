import os
from pathlib import Path
from typing import Any

from life.core.errors import LifeError

_DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/anthropic"
_DEFAULT_ENV_FILE = Path.home() / "life" / ".env"


def _read_env_file_value(path: Path, key: str) -> str | None:
    if not path.exists():
        return None
    prefix = f"{key}="
    for line in path.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#") or not s.startswith(prefix):
            continue
        value = s[len(prefix) :].strip().strip('"').strip("'")
        if value:
            return value
    return None


def build_env() -> dict[str, str]:
    env = os.environ.copy()
    zai_key = env.get("ZAI_API_KEY") or _read_env_file_value(_DEFAULT_ENV_FILE, "ZAI_API_KEY")
    if not zai_key:
        raise LifeError(f"ZAI_API_KEY is not set and was not found in {_DEFAULT_ENV_FILE}")

    env["ANTHROPIC_AUTH_TOKEN"] = zai_key
    env["ANTHROPIC_BASE_URL"] = env.get("ANTHROPIC_BASE_URL", _DEFAULT_BASE_URL)
    env["API_TIMEOUT_MS"] = env.get("API_TIMEOUT_MS", "3000000")
    env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = env.get(
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "1"
    )
    env.pop("ANTHROPIC_DEFAULT_OPUS_MODEL", None)
    env.pop("ANTHROPIC_DEFAULT_SONNET_MODEL", None)
    return env


def build_command(prompt: str) -> list[str]:
    return [
        "claude",
        "--print",
        "--verbose",
        "--output-format",
        "stream-json",
        "--dangerously-skip-permissions",
        prompt,
    ]


def _stringify_content(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text)
                else:
                    parts.append(str(item))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    if isinstance(value, dict):
        return str(value)
    return str(value)


def normalize_event(
    event: dict[str, Any], tool_map: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    if tool_map is None:
        tool_map = {}

    event_type = event.get("type")
    if event_type in {"system", "context_init"}:
        return [
            {
                "type": "system",
                "session_id": event.get("session_id") or event.get("sessionId") or "",
                "model": event.get("model") or "",
            }
        ]

    if event_type == "error" or (event_type == "result" and event.get("subtype") == "error"):
        message = (
            event.get("error") or event.get("message") or event.get("result") or "unknown error"
        )
        if isinstance(message, dict):
            message = message.get("message") or message.get("error") or str(message)
        return [{"type": "error", "message": str(message)}]

    if event_type == "assistant":
        msg = event.get("message", {})
        if not isinstance(msg, dict):
            return []
        out: list[dict[str, Any]] = []
        usage = msg.get("usage")
        if isinstance(usage, dict):
            out.append(
                {
                    "type": "usage",
                    "input_tokens": int(usage.get("input_tokens", 0)),
                    "output_tokens": int(usage.get("output_tokens", 0)),
                    "cache_tokens": int(usage.get("cache_read_input_tokens", 0))
                    + int(usage.get("cache_creation_input_tokens", 0)),
                }
            )

        blocks = msg.get("content")
        if not isinstance(blocks, list):
            return out

        for block in blocks:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type == "text":
                text = block.get("text")
                if isinstance(text, str) and text.strip():
                    out.append({"type": "assistant_text", "text": text.strip()})
            elif block_type == "tool_use":
                tool_use_id = str(block.get("id", ""))
                tool_name = str(block.get("name", ""))
                if tool_use_id and tool_name:
                    tool_map[tool_use_id] = tool_name
                out.append(
                    {
                        "type": "tool_call",
                        "tool_use_id": tool_use_id,
                        "tool_name": tool_name,
                        "args": block.get("input", {}),
                    }
                )
        return out

    if event_type == "user":
        msg = event.get("message", {})
        if not isinstance(msg, dict):
            return []
        content = msg.get("content")
        if not isinstance(content, list):
            return []
        out: list[dict[str, Any]] = []
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            tool_use_id = str(block.get("tool_use_id", ""))
            out.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "tool_name": block.get("tool_name") or tool_map.get(tool_use_id, ""),
                    "result": _stringify_content(block.get("content", "")),
                    "is_error": bool(block.get("is_error")),
                }
            )
        return out

    return []

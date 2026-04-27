"""Minimal claude stream-json parser — replaces atrace dependency."""

import json
import re
from pathlib import Path
from typing import Any

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_HOME = str(Path.home())


def ansi_strip(text: str) -> str:
    return _ANSI_RE.sub("", text)


# ANSI helpers
_R = "\033[0m"
_B = "\033[1m"
_DIM = "\033[2m"
_RED = "\033[38;5;203m"
_GREEN = "\033[38;5;114m"
_TEAL = "\033[38;5;80m"
_BLUE = "\033[38;5;111m"
_GRAY = "\033[38;5;245m"
_CORAL = "\033[38;5;209m"
_LIME = "\033[38;5;155m"
_FOREST = "\033[38;5;65m"
_SLATE = "\033[38;5;103m"
_WHITE = "\033[38;5;252m"
_PURPLE = "\033[38;5;141m"

_TOOL_COLORS: dict[str, str] = {
    "write": _LIME,
    "edit": _LIME,
    "run": _BLUE,
    "git": _PURPLE,
    "read": _TEAL,
    "grep": _TEAL,
    "glob": _TEAL,
    "ls": _TEAL,
    "fetch": _TEAL,
    "web": _TEAL,
    "cd": _GRAY,
}

_TOOL_DISPLAY: dict[str, str] = {
    "MultiEdit": "edit",
    "WebFetch": "fetch",
    "WebSearch": "web",
}

_BASH_MAP: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^cd\b"), "cd"),
    (re.compile(r"^git\b"), "git"),
    (re.compile(r"^(ls|exa)\b"), "ls"),
    (re.compile(r"^rg\b"), "grep"),
    (re.compile(r"^curl\b"), "fetch"),
    (re.compile(r"^uv\s+run\b"), "run"),
    (re.compile(r"^python[23]?\b"), "run"),
    (re.compile(r"^just\b"), "run"),
]


def _parse_bash(cmd: str) -> tuple[str, str]:
    base = cmd.strip().split("\n")[0].replace(_HOME, "~")
    for pat, name in _BASH_MAP:
        if pat.match(base):
            return name, re.sub(pat.pattern + r"\s*", "", base).strip()
    return "run", base


def _short(text: str, limit: int = 100) -> str:
    text = " ".join(text.strip().replace("\r", "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _stringify_content(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                t = item.get("text")
                parts.append(t if isinstance(t, str) else str(item))
        return "\n".join(parts)
    return str(value)


def _normalize(event: dict[str, Any], tool_map: dict[str, str]) -> list[dict[str, Any]]:
    t = event.get("type")

    if t in {"system", "context_init"}:
        return [{"type": "system", "model": event.get("model", "")}]

    if t == "error" or (t == "result" and event.get("subtype") == "error"):
        msg = event.get("error") or event.get("message") or event.get("result") or "unknown error"
        if isinstance(msg, dict):
            msg = msg.get("message") or str(msg)
        return [{"type": "error", "message": str(msg)}]

    if t == "assistant":
        msg = event.get("message", {})
        if not isinstance(msg, dict):
            return []
        out: list[dict[str, Any]] = []
        usage = msg.get("usage")
        if isinstance(usage, dict):
            out.append({
                "type": "usage",
                "input_tokens": int(usage.get("input_tokens", 0)),
                "output_tokens": int(usage.get("output_tokens", 0)),
            })
        for block in msg.get("content", []):
            if not isinstance(block, dict):
                continue
            bt = block.get("type")
            if bt == "text":
                text = block.get("text", "")
                if isinstance(text, str) and text.strip():
                    out.append({"type": "assistant_text", "text": text.strip()})
            elif bt == "tool_use":
                tid = str(block.get("id", ""))
                name = str(block.get("name", ""))
                if tid and name:
                    tool_map[tid] = name
                out.append({"type": "tool_call", "tool_use_id": tid, "tool_name": name, "args": block.get("input", {})})
        return out

    if t == "user":
        msg = event.get("message", {})
        if not isinstance(msg, dict):
            return []
        out = []
        for block in msg.get("content", []):
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            tid = str(block.get("tool_use_id", ""))
            out.append({
                "type": "tool_result",
                "tool_use_id": tid,
                "tool_name": block.get("tool_name") or tool_map.get(tid, ""),
                "result": _stringify_content(block.get("content", "")),
                "is_error": bool(block.get("is_error")),
            })
        return out

    return []


class StreamParser:
    def __init__(self, identity: str = "steward") -> None:
        self._identity = identity
        self._tool_map: dict[str, str] = {}
        self._pending: dict[str, dict[str, Any]] = {}
        self.ctx_tokens: int | None = None

    def parse_line(self, line: str) -> list[dict[str, Any]]:
        raw = line.strip()
        if not raw:
            return []
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(event, dict):
            return []
        out = []
        for entry in _normalize(event, self._tool_map):
            if entry.get("type") == "usage":
                tok = entry.get("input_tokens")
                if isinstance(tok, int) and tok > 0:
                    self.ctx_tokens = tok
            if entry.get("type") == "tool_call":
                tid = str(entry.get("tool_use_id", ""))
                if tid:
                    self._pending[tid] = entry
                out.append(entry)
            elif entry.get("type") == "tool_result":
                tid = str(entry.get("tool_use_id", ""))
                call = self._pending.pop(tid, None)
                if call:
                    out.append({**call, "_result": entry})
                if entry.get("is_error"):
                    out.append(entry)
            else:
                out.append(entry)
        return out

    def flush(self) -> list[dict[str, Any]]:
        out = list(self._pending.values())
        self._pending.clear()
        return out


def format_entry(entry: dict[str, Any], quiet_system: bool = True) -> str | None:
    kind = entry.get("type", "")

    if kind == "system":
        if quiet_system:
            return None
        return f"{_DIM}  session init{_R}"

    if kind == "assistant_text":
        tok = entry.get("_ctx_tokens")
        tok_str = f" {_GRAY}{tok // 1000}k{_R}" if isinstance(tok, int) and tok >= 1000 else ""
        text = _short(entry.get("text", ""), 120).lower()
        return f"  {_B}{_FOREST}hm…{_R}{tok_str} {_FOREST}{text}{_R}"

    if kind == "tool_call":
        raw_name = str(entry.get("tool_name") or "unknown")
        args = entry.get("args", {}) or {}
        name = _TOOL_DISPLAY.get(raw_name, raw_name.lower())
        if raw_name == "Bash":
            cmd = str(args.get("command", "")).split("\n")[0].replace(_HOME, "~")
            name, arg = _parse_bash(cmd)
            name = _TOOL_DISPLAY.get(name, name)
        elif raw_name in ("WebFetch",):
            arg = str(args.get("url", ""))
        elif raw_name in ("WebSearch",):
            arg = str(args.get("query", ""))
        else:
            arg = str(args.get("path") or args.get("file_path") or args.get("pattern") or "")
        color = _TOOL_COLORS.get(name, _GRAY)
        result = entry.get("_result")
        suffix = ""
        if isinstance(result, dict) and result.get("is_error"):
            err = _short(str(result.get("result", "")), 60)
            suffix = f" {_CORAL}{err}{_R}"
        return f"  {_B}{color}{name}{_R} {_GRAY}{_short(arg, 80)}{_R}{suffix}"

    if kind == "tool_result" and entry.get("is_error"):
        tool = str(entry.get("tool_name", ""))
        err = _short(str(entry.get("result", "")), 80)
        return f"  {_B}{_RED}oops.{_R} {_CORAL}{tool} {err}{_R}"

    if kind == "error":
        return f"  {_B}{_RED}error.{_R} {_CORAL}{_short(str(entry.get('message', '')), 200)}{_R}"

    if kind == "usage":
        in_tok = entry.get("input_tokens", 0)
        out_tok = entry.get("output_tokens", 0)
        if in_tok or out_tok:
            return f"  {_DIM}in={in_tok} out={out_tok}{_R}"

    return None

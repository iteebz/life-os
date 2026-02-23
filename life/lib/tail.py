import difflib
import json
import re
from pathlib import Path
from typing import cast

from .ansi import (
    ANSI,
    blue,
    bold,
    coral,
    dim,
    forest,
    gray,
    green,
    highlight_path,
    highlight_references,
    lime,
    purple,
    red,
    slate,
    strip_markdown,
    teal,
    white,
)
from .providers import glm

_HOME = str(Path.home())

_TOOL_DISPLAY = {
    "MultiEdit": "edit",
    "WebFetch": "fetch",
    "WebSearch": "web",
}

_TOOL_COLORS = {
    "write": lime,
    "edit": lime,
    "run": blue,
    "git": purple,
    "cd": gray,
    "read": teal,
    "grep": teal,
    "glob": teal,
    "ls": teal,
    "fetch": teal,
    "web": teal,
}

_BASH_PRIMITIVES: list[tuple[re.Pattern[str], str, str | None]] = [
    (re.compile(r"^cd\b"), "cd", r"^cd\s+"),
    (re.compile(r"^git\b"), "git", r"^git\s+"),
    (re.compile(r"^rg\b"), "grep", r"^rg\s+"),
    (re.compile(r"^(ls|exa)(?:\s+|$)"), "ls", r"^(ls|exa)(?:\s+|$)"),
    (re.compile(r"^curl\b"), "fetch", r"^curl\s+"),
    (re.compile(r"^uv\s+run\s+"), "run", r"^uv\s+run\s+"),
    (re.compile(r"^python[23]?\b"), "run", r"^python[23]?\s+"),
    (re.compile(r"^just\b"), "run", r"^just\s+"),
    (re.compile(r"^(npm|pnpm|yarn)\s+run\s+"), "run", r"^(npm|pnpm|yarn)\s+run\s+"),
    (re.compile(r"^(npm|pnpm|yarn)\b"), "run", r"^(npm|pnpm|yarn)\s+"),
    (re.compile(r"^(make|cargo|go)\b"), "run", r"^(make|cargo|go)\s+"),
]

_STRIP_CACHE: dict[str, re.Pattern[str]] = {}
_CHAIN_RE = re.compile(r'\s*&&\s*(?=(?:[^"]*"[^"]*")*[^"]*$)(?=(?:[^\']*\'[^\']*\')*[^\']*$)')
_PIPE_RE = re.compile(r"\s+(?:[|&]|[12]?>[>&]?)")


def _strip_re(pattern: str) -> re.Pattern[str]:
    if pattern not in _STRIP_CACHE:
        _STRIP_CACHE[pattern] = re.compile(pattern)
    return _STRIP_CACHE[pattern]


def _split_chain(cmd: str) -> list[str]:
    parts = _CHAIN_RE.split(cmd.strip())
    return [p.strip() for p in parts if p.strip()]


_CWD = str(Path.cwd())


def _parse_bash(cmd: str) -> tuple[str, str]:
    cleaned = cmd.strip()
    base_cmd = cleaned
    pipe_match = _PIPE_RE.search(cleaned)
    if pipe_match:
        base_cmd = cleaned[: pipe_match.start()].strip()
    for pat, name, strip in _BASH_PRIMITIVES:
        if not pat.match(base_cmd):
            continue
        arg = _strip_re(strip).sub("", base_cmd).strip() if strip else base_cmd
        return name, arg
    return "run", cleaned


def _short(value: object, limit: int = 120) -> str:
    text = str(value).strip().replace("\r", "")
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _tool_arg(raw_name: str, args: dict[str, object]) -> str:
    if raw_name == "WebFetch":
        return str(args.get("url", ""))
    if raw_name == "WebSearch":
        return str(args.get("query", ""))
    cmd = args.get("command")
    if isinstance(cmd, str) and cmd:
        return cmd
    path = args.get("path") or args.get("file_path")
    pattern = args.get("pattern")
    if raw_name == "Grep":
        if isinstance(path, str) and isinstance(pattern, str) and path and pattern:
            return f"{path} {pattern}"
        if isinstance(pattern, str) and pattern:
            return pattern
        if isinstance(path, str):
            return path
    if isinstance(path, str) and path:
        return path
    if isinstance(pattern, str) and pattern:
        return pattern
    items = list(args.items())[:2]
    return ", ".join(f"{k}={_short(v, 40)}" for k, v in items)


_RUN_NAMES = {"run", "git"}
_CLEAN_RUN_RE = re.compile(r"^\./.venv/bin/(?:python[23]?\s+-m\s+)?")


def _format_tool_arg(name: str, arg: str) -> str:
    if name in _RUN_NAMES:
        cleaned = arg.strip()
        if " || " in cleaned:
            cleaned = cleaned.split(" || ")[-1].strip()
        cleaned = _CLEAN_RUN_RE.sub("", cleaned)
        cleaned = re.sub(r"\s+2>&1(?=\s|$)", "", cleaned)
        if cleaned.startswith("just "):
            cleaned = cleaned[5:].strip()
        return slate(highlight_references(cleaned, ANSI.SLATE))
    if "/" in arg or "~" in arg:
        return highlight_references(highlight_path(arg, ANSI.WHITE), ANSI.WHITE)
    return white(highlight_references(arg, ANSI.WHITE))


def _edit_suffix(raw_name: str, args: dict[str, object]) -> str:
    edits: list[dict[str, object]] = []
    if raw_name == "MultiEdit":
        raw = args.get("edits", [])
        edits = list(raw) if isinstance(raw, list) else []
    elif raw_name == "Edit":
        edits = [
            {"old_string": args.get("old_string", ""), "new_string": args.get("new_string", "")}
        ]
    elif raw_name == "Write":
        content = args.get("content")
        if isinstance(content, str):
            n = len(content.split("\n"))
            return f" {lime(str(n))}"
        return ""
    total_add = total_rem = 0
    for edit in edits:
        old = edit.get("old_string", "")
        new = edit.get("new_string", "")
        if isinstance(old, str) and isinstance(new, str):
            old_lines = old.rstrip().split("\n") if old else []
            new_lines = new.rstrip().split("\n") if new else []
            for line in difflib.unified_diff(old_lines, new_lines, lineterm="", n=0):
                if line.startswith(("---", "+++", "@@")):
                    continue
                if line.startswith("-"):
                    total_rem += 1
                elif line.startswith("+"):
                    total_add += 1
    parts = []
    if total_add:
        parts.append(lime(f"+{total_add}"))
    if total_rem:
        parts.append(coral(f"-{total_rem}"))
    return f" ({' '.join(parts)})" if parts else ""


def _format_tool_call(raw_name: str, args: dict[str, object]) -> str:
    name = _TOOL_DISPLAY.get(raw_name, raw_name.lower())
    is_bash = raw_name == "Bash"
    arg = _tool_arg(raw_name, args)
    arg = arg.replace(_HOME, "~").replace(_CWD, ".")

    if is_bash:
        name, arg = _parse_bash(arg.split("\n")[0])
        name = _TOOL_DISPLAY.get(name, name)

    suffix = ""
    if raw_name in ("Edit", "MultiEdit", "Write"):
        suffix = _edit_suffix(raw_name, args)

    color_fn = _TOOL_COLORS.get(name, gray)
    label = bold(color_fn(name))
    arg_fmt = _format_tool_arg(name, arg[:100]) if arg else ""
    return f"  {label} {arg_fmt}{suffix}"


def _format_bash_chain(raw_name: str, args: dict[str, object]) -> list[str] | None:
    if raw_name != "Bash":
        return None
    cmd = str(args.get("command", "")).split("\n")[0].replace(_HOME, "~").replace(_CWD, ".")
    subcmds = _split_chain(cmd)
    if len(subcmds) <= 1:
        return None
    lines = []
    for sub in subcmds:
        name, arg = _parse_bash(sub)
        if name == "cd":
            continue
        name = _TOOL_DISPLAY.get(name, name)
        color_fn = _TOOL_COLORS.get(name, gray)
        label = bold(color_fn(name))
        arg_fmt = _format_tool_arg(name, arg[:80]) if arg else ""
        lines.append(f"  {label} {arg_fmt}")
    return lines if lines else None


class StreamParser:
    def __init__(self) -> None:
        self._tool_map: dict[str, str] = {}

    def parse_line(self, line: str) -> list[dict[str, object]]:
        raw = line.strip()
        if not raw:
            return []
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            return [{"type": "raw", "raw": raw}]
        if not isinstance(event, dict):
            return [{"type": "raw", "raw": raw}]
        normalized = glm.normalize_event(event, tool_map=self._tool_map)
        if normalized:
            return normalized
        return [{"type": "raw", "raw": raw}]


def format_entry(entry: dict[str, object], quiet_system: bool = False) -> str | None:
    kind = str(entry.get("type", ""))

    if kind == "assistant_text":
        text = str(entry.get("text", ""))
        text = strip_markdown(text.replace("\n", " "))
        if len(text) > 120:
            text = text[:120] + "…"
        text = highlight_references(text.lower(), ANSI.FOREST)
        return f"  {bold(green('hm...'))} {forest(text)}"

    if kind == "tool_call":
        raw_name = str(entry.get("tool_name") or "unknown")
        args = entry.get("args", {})
        if not isinstance(args, dict):
            args = {}
        chain = _format_bash_chain(raw_name, args)
        if chain:
            return "\n".join(chain)
        return _format_tool_call(raw_name, args)

    if kind == "tool_result":
        is_error = bool(entry.get("is_error"))
        if is_error:
            tool_name = str(entry.get("tool_name") or "")
            result_text = str(entry.get("result", ""))
            err_line = result_text.replace(_HOME, "~").split("\n")[0][:80]
            label = f"{tool_name.lower()} " if tool_name else ""
            return f"  {bold(red('oops.'))} {coral(label + err_line)}"
        return None

    if kind == "system":
        if quiet_system:
            return None
        session_id = _short(entry.get("session_id", ""), 8)
        model = _short(entry.get("model", ""), 40)
        return dim(f"  session {session_id or '-'} model={model or '-'}")

    if kind == "usage":
        in_tok = cast(int, entry.get("input_tokens") or 0)
        out_tok = cast(int, entry.get("output_tokens") or 0)
        cache_tok = cast(int, entry.get("cache_tokens") or 0)
        if in_tok == 0 and out_tok == 0 and cache_tok == 0:
            return None
        return dim(f"  in={in_tok} out={out_tok} cache={cache_tok}")

    if kind == "error":
        return f"  {bold(red('error.'))} {coral(_short(str(entry.get('message', '')), 200))}"

    if kind == "raw":
        return None

    return None

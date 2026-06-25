"""Markdown frontmatter parsing. Ported from spacebrr/api/infra/frontmatter.py."""

import re
from pathlib import Path

_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def field(text: str, key: str) -> str | None:
    """Return the value of a frontmatter key, or None if absent."""
    m = _RE.match(text)
    if not m:
        return None
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        if k.strip() == key:
            return v.strip() or None
    return None


def parse(text: str) -> dict[str, str]:
    """Parse all frontmatter key-value pairs into a dict."""
    m = _RE.match(text)
    if not m:
        return {}
    result: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        k = k.strip()
        v = v.strip()
        if k and v:
            result[k] = v
    return result


def has_field(text: str, key: str) -> bool:
    """Return True if the frontmatter key is present, even with empty value."""
    m = _RE.match(text)
    if not m:
        return False
    return any(line.partition(":")[0].strip() == key for line in m.group(1).splitlines() if ":" in line)


def title(path: "Path | str") -> str:
    """Extract title from first H1, fallback to stem."""
    p = Path(path)
    text = p.read_text()
    # skip frontmatter block
    m = _RE.match(text)
    body = text[m.end() :] if m else text
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return p.stem.replace("-", " ")

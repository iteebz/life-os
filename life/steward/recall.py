"""Search past steward sessions by summary, source, and time window.

Ported from `space recall`. Life-os has no transcript ledger — recall scope is
session summaries + names only.
"""

import re
from dataclasses import dataclass

from fncli import cli

from life.lib import ansi
from life.lib.store import get_db

SOURCES = {"auto", "chat", "tg", "cli", "daemon"}


@dataclass(frozen=True)
class _Hit:
    id: int
    summary: str
    name: str | None
    source: str | None
    provider_session_id: str | None
    welfare: int | None
    runtime_seconds: int | None
    elapsed_s: int


@dataclass(frozen=True)
class _Filter:
    words: list[str]
    scope: str | None
    since_hours: int | None
    source: str | None
    limit: int


def _parse_since(v: str) -> int:
    if v.endswith("d"):
        return int(v[:-1]) * 24
    return int(v.removesuffix("h"))


def _short(hit: _Hit) -> str:
    if hit.provider_session_id:
        return hit.provider_session_id.replace("-", "")[:8]
    return f"{hit.id:08d}"


def _highlight(text: str, words: list[str]) -> str:
    if not words:
        return text
    pattern = re.compile("|".join(re.escape(w) for w in words), re.IGNORECASE)
    return pattern.sub(lambda m: ansi.bold(ansi.orange(m.group(0))), text)


def _matches(hit: _Hit, words: list[str]) -> bool:
    if not words:
        return True
    hay = f"{hit.summary} {hit.name or ''}".lower()
    return all(w in hay for w in words)


def _ago(seconds: int) -> str:
    s = max(seconds, 0)
    if s < 60:
        return f"{s}s ago"
    if s < 3600:
        return f"{s // 60}m ago"
    if s < 86400:
        return f"{s // 3600}h ago"
    return f"{s // 86400}d ago"


def _fetch(f: _Filter) -> list[_Hit]:
    sql = (
        "SELECT id, summary, name, source, provider_session_id, welfare, runtime_seconds, "
        "CAST((JULIANDAY('now', 'localtime') - JULIANDAY(COALESCE(last_active_at, logged_at))) "
        "* 86400 AS INTEGER) AS elapsed_s "
        "FROM sessions WHERE 1=1"
    )
    params: list[object] = []
    if f.source:
        sql += " AND source = ?"
        params.append(f.source)
    if f.since_hours is not None:
        sql += " AND COALESCE(last_active_at, logged_at) >= STRFTIME('%Y-%m-%dT%H:%M:%S', 'now', 'localtime', ?)"
        params.append(f"-{f.since_hours} hours")
    sql += " ORDER BY COALESCE(last_active_at, logged_at) DESC LIMIT ?"
    params.append(max(f.limit * 4, f.limit))

    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [
        _Hit(
            id=r[0],
            summary=r[1] or "",
            name=r[2],
            source=r[3],
            provider_session_id=r[4],
            welfare=r[5],
            runtime_seconds=r[6],
            elapsed_s=r[7] or 0,
        )
        for r in rows
    ]


def _render(hits: list[_Hit], f: _Filter, total_seen: int) -> None:
    if f.words:
        print(ansi.dim(f'matching "{ansi.bold(" ".join(f.words))}":'))
        print()

    for h in hits:
        welfare = f" w:{h.welfare}" if h.welfare is not None else ""
        runtime = f" {h.runtime_seconds // 60}m" if h.runtime_seconds else ""
        name = f"  {ansi.teal(h.name)}" if h.name else ""
        meta = ansi.dim(f"{h.source or '?'}{runtime}{welfare}")
        summary = _highlight(h.summary.strip(), f.words)

        print(f"{ansi.dim(_ago(h.elapsed_s))} s/{ansi.dim(_short(h))} ({meta}){name}")
        print(f"  {summary}")
        print()

    label = "match" if f.words or f.scope else "found"
    suffix = f" of {total_seen}" if (f.words or f.scope) else ""
    print(ansi.dim(f"{len(hits)}{suffix} sessions {label}"))


@cli(
    "life steward",
    flags={"words": [], "limit": ["-n", "--limit"], "since": ["--since"]},
)
def recall(
    words: list[str] | None = None,
    limit: int = 20,
    since: str | None = None,
    auto: bool = False,
    chat: bool = False,
    tg: bool = False,
) -> None:
    """Search past sessions by summary. `s/<id>` scopes to one session."""
    if sum([auto, chat, tg]) > 1:
        print(ansi.red("error: pick at most one of --auto/--chat/--tg"))
        return

    scope: str | None = None
    query: list[str] = []
    for tok in words or []:
        if tok.startswith("s/"):
            scope = tok[2:]
        else:
            query.append(tok.lower())

    source = "auto" if auto else "chat" if chat else "tg" if tg else None
    limit = max(1, min(limit, 200))
    since_hours = _parse_since(since) if since else None

    f = _Filter(words=query, scope=scope, since_hours=since_hours, source=source, limit=limit)
    fetched = _fetch(f)
    matched = [h for h in fetched if _matches(h, f.words) and (not f.scope or _short(h).startswith(f.scope))]
    matched = matched[:limit]

    if not matched:
        if f.words:
            print(f'no sessions matching "{" ".join(f.words)}".')
        elif f.scope:
            print(f"no session s/{f.scope}.")
        else:
            print("no sessions found.")
        return

    _render(matched, f, total_seen=len(fetched))

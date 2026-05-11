"""life steward notes — daily timeline of sessions, observations, and commits."""

from __future__ import annotations

import subprocess
from datetime import date, datetime
from pathlib import Path

from fncli import cli

from . import get_observations, get_sessions

# ANSI colours
_RESET = "\033[0m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_CYAN = "\033[36m"
_YELLOW = "\033[33m"
_GREEN = "\033[32m"
_MAGENTA = "\033[35m"
_BLUE = "\033[34m"


def _midnight(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 0, 0, 0)


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _commits_for_day(since: datetime, until: datetime) -> list[tuple[str, str, str]]:
    """Return list of (repo_label, time_str, subject) for commits in the window."""
    life_root = Path.home() / "life"
    repos: list[tuple[str, Path]] = [
        ("life", life_root),
        ("life-os", life_root / "life-os"),
        ("taxing", life_root / "taxing"),
    ]
    repos_dir = life_root / "repos"
    if repos_dir.exists():
        repos.extend((p.name, p) for p in sorted(repos_dir.iterdir()) if p.is_dir() and (p / ".git").exists())

    results: list[tuple[datetime, str, str, str]] = []
    for label, repo in repos:
        if not (repo / ".git").exists():
            continue
        try:
            out = subprocess.run(
                [
                    "git",
                    "log",
                    f"--after={since.isoformat()}",
                    f"--before={until.isoformat()}",
                    "--format=%ct|%an|%s",
                ],
                cwd=repo,
                capture_output=True,
                text=True,
            )
            for line in out.stdout.splitlines():
                parts = line.split("|", 2)
                if len(parts) < 3:
                    continue
                ts, author, subject = parts
                dt = datetime.fromtimestamp(int(ts))
                results.append((dt, label, author.strip(), subject.strip()))
        except Exception:  # noqa: S110
            pass

    results.sort(key=lambda x: x[0])
    return [
        (label, dt.strftime("%H:%M"), f"{subject}  {_DIM}({author}){_RESET}") for dt, label, author, subject in results
    ]


@cli("life", flags={"date": ["-d", "--date"]})
@cli("life steward", flags={"date": ["-d", "--date"]})
def notes(date: str | None = None) -> None:
    """Daily timeline — sessions, observations, and commits"""
    if date:
        target = _parse_date(date)
    else:
        target = datetime.now().date()

    since = _midnight(target)
    until = _midnight(target) if date else datetime.now()
    if date:
        # show full day
        until = datetime(target.year, target.month, target.day, 23, 59, 59)

    now = datetime.now()

    # header
    label = "today" if target == now.date() else target.strftime("%a %d %b %Y").lower()
    print(f"\n{_BOLD}steward notes — {label}{_RESET}\n")

    # collect events: (datetime, kind, text)
    events: list[tuple[datetime, str, str]] = []

    # sessions
    sessions = get_sessions(limit=100)
    for s in sessions:
        ts = s.started_at or s.logged_at
        if since <= ts <= until:
            src = f"  {_DIM}[{s.source or 'cli'}]{_RESET}" if s.source else ""
            welfare = f"  {_GREEN}welfare={s.welfare}{_RESET}" if s.welfare else ""
            events.append((ts, "session", f"{s.summary}{src}{welfare}"))

    # observations
    obs = get_observations(limit=200)
    for o in obs:
        ts = o.logged_at
        if since <= ts <= until:
            tag = f"  {_MAGENTA}#{o.tag}{_RESET}" if o.tag else ""
            events.append((ts, "observe", f"{o.body}{tag}"))

    # commits
    for repo_label, time_str, subject in _commits_for_day(since, until):
        # parse time_str back to datetime for sorting
        h, m = map(int, time_str.split(":"))
        commit_dt = datetime(target.year, target.month, target.day, h, m)
        events.append((commit_dt, "commit", f"{_DIM}{repo_label}{_RESET}  {subject}"))

    if not events:
        print(f"  {_DIM}nothing logged{_RESET}\n")
        return

    events.sort(key=lambda x: x[0])

    kind_fmt = {
        "session": (_CYAN, "session"),
        "observe": (_YELLOW, "observe"),
        "commit": (_BLUE, " commit"),
    }

    for dt, kind, text in events:
        colour, label = kind_fmt[kind]
        time_str = dt.strftime("%H:%M")
        print(f"  {_DIM}{time_str}{_RESET}  {colour}{label}{_RESET}  {text}")

    print()

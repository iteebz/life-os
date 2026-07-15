"""Ambient context signals injected on PreToolUse."""

import contextlib
import os
import subprocess
import time
from pathlib import Path

from life.habit import get_habits
from life.mood import get_recent_moods
from life.task import get_tasks
from lifeos.core.comms import events
from lifeos.core.lib.clock import today
from lifeos.steward.ping import drain

_LIFE_ROOT = Path.home() / "life"
_LIFE_OS_ROOT = _LIFE_ROOT / "life-os"


def _state_path() -> Path:
    key = os.environ.get("STEWARD_SESSION_ID") or str(os.getppid())
    return Path(os.environ.get("TMPDIR", "/tmp")) / f".life_hook_{key}"


def load_state() -> dict[str, str]:
    path = _state_path()
    if not path.exists():
        return {}
    fields: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            fields[k] = v
    return fields


def save_state(state: dict[str, str]) -> None:
    _state_path().write_text("\n".join(f"{k}={v}" for k, v in state.items()) + "\n")


def throttled(state: dict[str, str], key: str, interval: int) -> bool:
    last = state.get(key)
    if last is None:
        return False
    return (time.time() - float(last)) < interval


def touch(state: dict[str, str], key: str) -> None:
    state[key] = str(time.time())


def render_inbox(rows) -> list[str]:
    return [f"  [{ch}] {name or '?'}: {(body or '')[:200]}" for _id, ch, name, body, _ts in rows]


def inbox_signal(state: dict[str, str], parts: list[str]) -> None:
    rows = events.drain_inbox()
    if rows:
        parts.append("inbox:\n" + "\n".join(render_inbox(rows)))


def ping_signal(state: dict[str, str], parts: list[str]) -> None:
    last = int(state.get("last_ping_id", "0"))
    with contextlib.suppress(Exception):
        pings, max_id = drain(last)
        state["last_ping_id"] = str(max_id)
        for _, msg in pings:
            parts.append(f"[steward ping]: {msg}")


def habit_status(state: dict[str, str], parts: list[str]) -> None:
    if throttled(state, "habits_at", 60):
        return
    touch(state, "habits_at")
    habits = get_habits()
    if not habits:
        return
    today_date = today()
    done, pending = [], []
    for h in habits:
        if h.cadence != "daily":
            continue
        if "vice" in (h.tags or []):
            continue
        checks_today = [c for c in h.checks if c.date() == today_date]
        (done if checks_today else pending).append(h.content)
    if not pending and not done:
        return
    line = f"habits: {len(done)}/{len(done) + len(pending)} done"
    if pending:
        line += f" — pending: {', '.join(pending[:5])}"
        if len(pending) > 5:
            line += f" +{len(pending) - 5} more"
    parts.append(line)


def mood_signal(state: dict[str, str], parts: list[str]) -> None:
    if throttled(state, "mood_at", 300):
        return
    touch(state, "mood_at")
    moods = get_recent_moods(hours=12)
    if not moods:
        return
    latest = moods[0]
    bar = "█" * latest.score + "░" * (5 - latest.score)
    label = f"  {latest.label}" if latest.label else ""
    parts.append(f"mood: {bar} {latest.score}/5{label}")


def active_tasks(state: dict[str, str], parts: list[str]) -> None:
    if throttled(state, "tasks_at", 60):
        return
    touch(state, "tasks_at")
    tasks = get_tasks()
    if not tasks:
        return
    lines = [f"  · {t.content}" for t in tasks[:5]]
    header = f"tasks ({len(tasks)} open):"
    if len(tasks) > 5:
        lines.append(f"  +{len(tasks) - 5} more")
    parts.append(header + "\n" + "\n".join(lines))


def dirty_state(state: dict[str, str], parts: list[str]) -> None:
    if state.get("dirty_shown"):
        return
    state["dirty_shown"] = "1"
    with contextlib.suppress(Exception):
        result = subprocess.run(
            ["git", "-C", str(_LIFE_ROOT), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
        if lines:
            summary = "\n".join(lines[:10])
            if len(lines) > 10:
                summary += f"\n... +{len(lines) - 10} more"
            parts.append(f"~/life dirty ({len(lines)} files):\n{summary}")


def life_os_commits(state: dict[str, str], parts: list[str]) -> None:
    with contextlib.suppress(Exception):
        result = subprocess.run(
            ["git", "-C", str(_LIFE_OS_ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        head = result.stdout.strip()
        if not head:
            return
        last = state.get("life_os_head")
        state["life_os_head"] = head
        if last is None or last == head:
            return
        log = subprocess.run(
            ["git", "-C", str(_LIFE_OS_ROOT), "log", "--oneline", f"{last}..{head}"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        commits = log.stdout.strip()
        if commits:
            parts.append(f"life-os new commits:\n{commits[:400]}")


ALL_SIGNALS = (dirty_state, life_os_commits, inbox_signal, ping_signal, habit_status, mood_signal, active_tasks)

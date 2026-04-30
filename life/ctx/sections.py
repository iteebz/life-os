"""Wake section renderers. Each returns a string (empty = omit)."""

from __future__ import annotations

import os
import re
import subprocess
import time
from datetime import date, datetime
from pathlib import Path

from life.comms.accounts import list_accounts
from life.comms.drafts import list_pending_drafts
from life.comms.events import peek_inbox
from life.comms.messages.telegram import get_history
from life.comms.services import get_email_adapter
from life.contacts import get_stale_contacts
from life.feedback import build_feedback_snapshot, render_feedback_headline
from life.habit import get_habits
from life.improvements import get_improvements
from life.lib.clock import today
from life.lib.dates import list_dates
from life.lib.format import format_elapsed
from life.lib.ids import short
from life.mood import get_recent_moods
from life.skills import list_skills
from life.steward import get_observations, get_sessions, latest_handover
from life.task import get_all_tasks, get_tasks

from .fragments import STEWARD_BIRTHDAY


def render_header() -> str:
    age_days = (datetime.now() - STEWARD_BIRTHDAY).days
    now = datetime.now()
    return f"STEWARD — day {age_days}  |  {now.strftime('%a %d %b %Y  %I:%M%p').lower()}"


def render_steward_tasks() -> str:
    tasks = [t for t in get_tasks(include_steward=True) if t.steward]
    if not tasks:
        return ""
    lines = ["STEWARD TASKS:"]
    lines.extend(f"  · {t.content}" for t in tasks)
    return "\n".join(lines)


def render_feedback() -> str:
    snapshot = build_feedback_snapshot(
        all_tasks=get_all_tasks(),
        pending_tasks=get_tasks(),
        habits=get_habits(),
        today=today(),
    )
    return render_feedback_headline(snapshot)


def render_handover() -> str:
    text = latest_handover()
    if not text:
        return ""
    return f"** HANDOVER ** {text}\n   (clear with `life steward handover-clear` after acting)"


def render_last_session() -> str:
    sessions = get_sessions(limit=1)
    if not sessions:
        return ""
    s = sessions[0]
    rel = format_elapsed(s.logged_at, datetime.now())
    return f"LAST LIFE ({rel}): {s.summary}"


def render_contracts() -> str:
    path = Path.home() / "life" / "steward" / "contracts.md"
    if not path.exists():
        return ""
    text = path.read_text()
    blocks = re.split(r"^## ", text, flags=re.MULTILINE)
    contracts = []
    for block in blocks[1:]:
        lines = block.splitlines()
        name = lines[0].strip()
        ratified = next((ln.split("**ratified:**")[1].strip() for ln in lines if "**ratified:**" in ln), "")
        status = next((ln.split("**status:**")[1].strip() for ln in lines if "**status:**" in ln), "")
        contracts.append((name, ratified, status))
    if not contracts:
        return ""
    out = ["CONTRACTS:"]
    for name, ratified, status in contracts:
        flag = "  !" if not ratified or ratified == "—" else "   "
        out.append(f"{flag} {name:<14}  {status}")
    return "\n".join(out)


def render_observations() -> str:
    now = datetime.now()
    today_d = date.today()
    recent = get_observations(limit=40)
    tasks = get_tasks()

    upcoming = [o for o in recent if o.about_date and o.about_date >= today_d]
    fresh = [o for o in recent if not o.about_date and (now - o.logged_at).total_seconds() < 86400]
    active_tags = {tag for t in tasks for tag in (getattr(t, "tags", None) or [])}
    tagged: list = []  # type: ignore[type-arg]
    horizon = 86400 * 3
    seen: set[str] = {o.id for o in fresh} | {o.id for o in upcoming}
    for tag in active_tags:
        for o in get_observations(limit=5, tag=tag):
            if o.id in seen:
                continue
            if o.about_date and o.about_date < today_d:
                continue
            if not o.about_date and (now - o.logged_at).total_seconds() > horizon:
                continue
            tagged.append(o)
            seen.add(o.id)

    upcoming_sorted = sorted(upcoming, key=lambda o: o.about_date or today_d)
    all_obs = upcoming_sorted + sorted(fresh + tagged, key=lambda o: o.logged_at, reverse=True)
    if not all_obs:
        return ""
    out = ["OBSERVATIONS:"]
    for o in all_obs:
        if o.about_date:
            days = (o.about_date - today_d).days
            rel = "today" if days == 0 else "tomorrow" if days == 1 else f"in {days}d"
        else:
            rel = format_elapsed(o.logged_at, now)
        tag_str = f" #{o.tag}" if o.tag else ""
        out.append(f"  {rel:<10}  {o.body}{tag_str}")
    return "\n".join(out)


def render_dates() -> str:
    upcoming = [d for d in list_dates() if 0 <= d["days_until"] <= 30]
    if not upcoming:
        return ""
    out = ["DATES:"]
    for d in upcoming:
        days = d["days_until"]
        when = "today" if days == 0 else f"in {days}d"
        type_str = f"  [{d['type']}]" if d["type"] != "other" else ""
        out.append(f"  {when:<10}  {d['name']}{type_str}")
    return "\n".join(out)


def render_contacts() -> str:
    stale = get_stale_contacts()
    if not stale:
        return ""
    out = ["CONTACTS (overdue):"]
    for contact, days in stale:
        label = "never" if days is None else f"{days}d ago"
        out.append(f"  {contact.name:<12} {label:<10}  (every {contact.cadence_days}d)")
    return "\n".join(out)


def render_improvements() -> str:
    items = get_improvements()
    if not items:
        return ""
    out = ["IMPROVEMENTS:"]
    out.extend(f"  [{short('i', i.id)}] {i.body}" for i in items[:5])
    return "\n".join(out)


def render_skills() -> str:
    skills = list_skills()
    if not skills:
        return ""
    width = max(len(s.name) for s in skills)
    out = ["SKILLS (load with `life skill <name>`):"]
    for s in skills:
        when = f"  {s.when}" if s.when else ""
        out.append(f"  {s.name:<{width}}{when}")
    return "\n".join(out)


def render_mood() -> str:
    recent = get_recent_moods(hours=24)
    if not recent:
        return "MOOD: none logged — consider asking"
    latest = recent[0]
    rel = format_elapsed(latest.logged_at, datetime.now())
    bar = "█" * latest.score + "░" * (5 - latest.score)
    label = f"  {latest.label}" if latest.label else ""
    out = [f"MOOD ({rel}): {bar}  {latest.score}/5{label}"]
    if len(recent) > 1:
        out.append(f"  ({len(recent)} entries last 24h)")
    return "\n".join(out)


def _tracked_repos() -> list[tuple[str, Path]]:
    life_root = Path.home() / "life"
    repos: list[tuple[str, Path]] = [
        ("life", life_root),
        ("life-os", life_root / "life-os"),
        ("taxing", life_root / "taxing"),
    ]
    repos_dir = life_root / "repos"
    if repos_dir.exists():
        repos.extend((p.name, p) for p in sorted(repos_dir.iterdir()) if p.is_dir() and (p / ".git").exists())
    return repos


def render_commits() -> str:
    out = ["COMMIT STATS (7d):"]
    now_ts = time.time()
    since_arg = "--since=7 days ago"
    for label, repo in _tracked_repos():
        if not (repo / ".git").exists():
            continue
        try:
            log_result = subprocess.run(
                ["git", "log", since_arg, "--format=%an"],
                cwd=repo,
                capture_output=True,
                text=True,
            )
            last_result = subprocess.run(
                ["git", "log", "-1", "--format=%ct %s"],
                cwd=repo,
                capture_output=True,
                text=True,
            )
            dirty_result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo,
                capture_output=True,
                text=True,
            )
            authors: dict[str, int] = {}
            for line in log_result.stdout.splitlines():
                name = line.strip()
                if name:
                    authors[name] = authors.get(name, 0) + 1
            total = sum(authors.values())
            dirty = "~" if dirty_result.stdout.strip() else " "
            last_msg = ""
            if last_result.returncode == 0 and last_result.stdout.strip():
                ct_str, _, msg = last_result.stdout.strip().partition(" ")
                secs = now_ts - int(ct_str)
                if secs < 3600:
                    age = f"{int(secs // 60)}m"
                elif secs < 86400:
                    age = f"{int(secs // 3600)}h"
                elif secs < 86400 * 7:
                    age = f"{int(secs // 86400)}d"
                else:
                    age = f"{int(secs // (86400 * 7))}w"
                last_msg = f"  {age:<4}  {msg[:50]}"
            author_parts = [f"{name} {n}" for name, n in sorted(authors.items(), key=lambda x: -x[1])]
            author_str = "  ".join(author_parts) if author_parts else "no commits"
            out.append(f"  {dirty} {label:<12}  {total:>3}c  {author_str:<36}{last_msg}")
        except Exception:
            out.append(f"    {label:<12}  (error)")
    return "\n".join(out) if len(out) > 1 else ""


def render_comms() -> str:
    try:
        accounts = list_accounts("email")
        if not accounts:
            return ""
        total_inbox = 0
        flagged_lines: list[str] = []
        for acct in accounts:
            try:
                adapter = get_email_adapter(acct["provider"])
                threads = adapter.list_threads(acct["email"], label="inbox", max_results=10)
                total_inbox += len(threads)
                flagged = adapter.list_threads(acct["email"], label="starred", max_results=5)
                for t in flagged:
                    sender = t.get("from", "?")[:20]
                    subj = t.get("subject", "(no subject)")[:40]
                    flagged_lines.append(f"  ★ {sender:<20}  {subj}")
            except Exception as e:
                flagged_lines.append(f"  [comms error: {e}]")
        drafts = list_pending_drafts()
        parts = [f"{total_inbox} in inbox"]
        if drafts:
            parts.append(f"{len(drafts)} draft{'s' if len(drafts) != 1 else ''} pending")
        out = [f"COMMS: {', '.join(parts)}", *flagged_lines]
        return "\n".join(out)
    except Exception as e:
        if os.environ.get("LIFE_DEBUG"):
            return f"COMMS: boot error — {e}"
        return ""


def render_telegram() -> str:
    try:
        all_recent = get_history(limit=30, hours=48)
    except Exception:
        return ""
    last_in = next((i for i, m in enumerate(all_recent) if m["direction"] == "in"), None)
    if last_in is not None:
        show = list(reversed(all_recent[: last_in + 1]))[-15:]
    elif all_recent:
        show = list(reversed(all_recent[:5]))
    else:
        return ""
    out = ["TELEGRAM:"]
    for m in show:
        direction = "→" if m["direction"] == "out" else "←"
        name = m["peer_name"] or m["peer"]
        ago = int(time.time() - m["timestamp"])
        if ago < 3600:
            rel = f"{ago // 60}m ago"
        elif ago < 86400:
            rel = f"{ago // 3600}h ago"
        else:
            rel = f"{ago // 86400}d ago"
        body = m["body"] if m["direction"] == "in" else m["body"][:80]
        photo = f" 📷 {m['image_path']}" if m.get("image_path") else ""
        out.append(f"  {rel:<10} {direction} {name}: {body}{photo}")
    return "\n".join(out)


def render_inbox() -> str:
    try:
        rows = peek_inbox()
        if not rows:
            return ""
        lines = [f"  [{ch}] {name or '?'}: {(body or '')[:200]}" for _id, ch, name, body, _ts in rows]
        return "INBOX:\n" + "\n".join(lines)
    except Exception:
        return ""


def render_xmit() -> str:
    try:
        result = subprocess.run(["xmit", "recv"], capture_output=True, text=True, timeout=5)
        out = result.stdout.strip()
        if not out or out == "no messages":
            return ""
        return f"XMIT (new messages):\n{out}"
    except Exception:
        return ""

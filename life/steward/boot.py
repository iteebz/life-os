import subprocess
import time
from datetime import date, datetime
from pathlib import Path

from fncli import cli

from ..db import init
from . import _rel, get_observations, get_sessions

STEWARD_BIRTHDAY = datetime(2026, 2, 18)


@cli("steward")
def boot():
    """Load life state and emit sitrep for interactive session start"""
    from ..habits import get_habits
    from ..improvements import get_improvements
    from ..lib.clock import today
    from ..metrics import build_feedback_snapshot, render_feedback_headline
    from ..mood import get_recent_moods
    from ..tasks import get_all_tasks, get_tasks

    age_days = (datetime.now() - STEWARD_BIRTHDAY).days
    now_local = datetime.now()
    print(f"STEWARD — day {age_days}  |  {now_local.strftime('%a %d %b %Y  %I:%M%p').lower()}\n")

    tasks = get_tasks()
    all_tasks = get_all_tasks()
    habits = get_habits()
    steward_tasks = [t for t in get_tasks(include_steward=True) if t.steward]
    if steward_tasks:
        print("STEWARD TASKS:")
        for t in steward_tasks:
            print(f"  · {t.content}")
        print()
    today_date = today()
    snapshot = build_feedback_snapshot(
        all_tasks=all_tasks, pending_tasks=tasks, habits=habits, today=today_date
    )
    print(render_feedback_headline(snapshot))

    sessions = get_sessions(limit=1)
    if sessions:
        s = sessions[0]
        now = datetime.now()
        secs = (now - s.logged_at).total_seconds()
        rel = _rel(secs)
        print(f"\nLAST SESSION ({rel}): {s.summary}")

    now = datetime.now()
    today_d = date.today()
    recent = get_observations(limit=40)

    upcoming_obs = [o for o in recent if o.about_date and o.about_date >= today_d]
    recent_obs = [
        o for o in recent if not o.about_date and (now - o.logged_at).total_seconds() < 86400
    ]
    active_tags = {tag for t in tasks for tag in (getattr(t, "tags", None) or [])}
    tagged_obs = []
    tag_horizon = 86400 * 3
    seen_ids: set[int] = {o.id for o in recent_obs} | {o.id for o in upcoming_obs}
    for tag in active_tags:
        for o in get_observations(limit=5, tag=tag):
            if o.id in seen_ids:
                continue
            if o.about_date and o.about_date < today_d:
                continue
            if not o.about_date and (now - o.logged_at).total_seconds() > tag_horizon:
                continue
            tagged_obs.append(o)
            seen_ids.add(o.id)

    upcoming_obs_sorted = sorted(upcoming_obs, key=lambda o: o.about_date or today_d)
    all_obs = upcoming_obs_sorted + sorted(
        recent_obs + tagged_obs, key=lambda o: o.logged_at, reverse=True
    )

    if all_obs:
        print("\nOBSERVATIONS:")
        for o in all_obs:
            if o.about_date:
                days_until = (o.about_date - today_d).days
                if days_until == 0:
                    rel = "today"
                elif days_until == 1:
                    rel = "tomorrow"
                else:
                    rel = f"in {days_until}d"
            else:
                rel = _rel((now - o.logged_at).total_seconds())
            tag_str = f" #{o.tag}" if o.tag else ""
            print(f"  {rel:<10}  {o.body}{tag_str}")

    from ..lib.dates import list_dates

    upcoming_dates = [d for d in list_dates() if 0 <= d["days_until"] <= 30]
    if upcoming_dates:
        print("\nDATES:")
        for d in upcoming_dates:
            days = d["days_until"]
            when = "today" if days == 0 else f"in {days}d"
            type_str = f"  [{d['type']}]" if d["type"] != "other" else ""
            print(f"  {when:<10}  {d['name']}{type_str}")

    open_improvements = get_improvements()
    if open_improvements:
        print("\nIMPROVEMENTS:")
        for i in open_improvements[:5]:
            print(f"  [{i.id}] {i.body}")

    recent_moods = get_recent_moods(hours=24)
    if recent_moods:
        latest = recent_moods[0]
        secs = (datetime.now() - latest.logged_at).total_seconds()
        rel = _rel(secs)
        bar = "█" * latest.score + "░" * (5 - latest.score)
        label_str = f"  {latest.label}" if latest.label else ""
        print(f"\nMOOD ({rel}): {bar}  {latest.score}/5{label_str}")
        if len(recent_moods) > 1:
            print(f"  ({len(recent_moods)} entries last 24h)")
    else:
        print("\nMOOD: none logged — consider asking")

    life_root = Path.home() / "life"
    tracked_repos: list[tuple[str, Path]] = [
        ("life", life_root),
        ("life-os", life_root / "life-os"),
        ("taxing", life_root / "taxing"),
    ]
    repos_dir = life_root / "repos"
    if repos_dir.exists():
        tracked_repos.extend(
            (p.name, p) for p in sorted(repos_dir.iterdir()) if p.is_dir() and (p / ".git").exists()
        )

    print("\nCOMMIT STATS (7d):")
    now_ts = time.time()
    since_arg = "--since=7 days ago"
    for label, repo in tracked_repos:
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

            author_parts = [
                f"{name} {n}" for name, n in sorted(authors.items(), key=lambda x: -x[1])
            ]
            author_str = "  ".join(author_parts) if author_parts else "no commits"
            print(f"  {dirty} {label:<12}  {total:>3}c  {author_str:<36}{last_msg}")
        except Exception:
            print(f"    {label:<12}  (error)")

    try:
        from ..comms.accounts import list_accounts
        from ..comms.drafts import list_pending_drafts

        email_accounts = list_accounts("email")
        if email_accounts:
            from ..comms.services import _get_email_adapter

            total_inbox = 0
            flagged_lines: list[str] = []
            for acct in email_accounts:
                try:
                    adapter = _get_email_adapter(acct["provider"])
                    threads = adapter.list_threads(acct["email"], label="inbox", max_results=10)
                    total_inbox += len(threads)
                    flagged = adapter.list_threads(acct["email"], label="starred", max_results=5)
                    for t in flagged:
                        sender = t.get("from", "?")[:20]
                        subj = t.get("subject", "(no subject)")[:40]
                        flagged_lines.append(f"  ★ {sender:<20}  {subj}")
                except Exception as e:
                    flagged_lines.append(f"  [comms error: {e}]")

            pending_drafts = list_pending_drafts()
            parts = [f"{total_inbox} in inbox"]
            if pending_drafts:
                parts.append(
                    f"{len(pending_drafts)} draft{'s' if len(pending_drafts) != 1 else ''} pending"
                )
            print(f"\nCOMMS: {', '.join(parts)}")
            for line in flagged_lines:
                print(line)
    except Exception as e:
        import os

        if os.environ.get("LIFE_DEBUG"):
            print(f"\nCOMMS: boot error — {e}")


def main():
    import sys

    from fncli import dispatch

    init()
    sys.exit(dispatch(["life", "steward", "boot", *sys.argv[1:]]))

import subprocess
import time
from datetime import date, datetime
from pathlib import Path

from fncli import cli

from life.db import init
from life.lib.format import format_elapsed
from life.lib.ids import short

from . import get_observations, get_sessions

STEWARD_BIRTHDAY = datetime(2026, 2, 18)


@cli("steward")
def wake():
    """Load life state and emit sitrep for interactive session start"""
    from life.feedback import build_feedback_snapshot, render_feedback_headline
    from life.habit import get_habits
    from life.improvements import get_improvements
    from life.lib.clock import today
    from life.mood import get_recent_moods
    from life.task import get_all_tasks, get_tasks

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
        rel = format_elapsed(s.logged_at, now)
        print(f"\nLAST LIFE ({rel}): {s.summary}")

    contracts_path = Path.home() / "life" / "steward" / "contracts.md"
    if contracts_path.exists():
        text = contracts_path.read_text()
        import re
        blocks = re.split(r"^## ", text, flags=re.MULTILINE)
        contracts = []
        for block in blocks[1:]:  # skip preamble
            lines = block.splitlines()
            name = lines[0].strip()
            ratified = next((ln.split("**ratified:**")[1].strip() for ln in lines if "**ratified:**" in ln), "")
            status = next((ln.split("**status:**")[1].strip() for ln in lines if "**status:**" in ln), "")
            contracts.append((name, ratified, status))
        if contracts:
            print("\nCONTRACTS:")
            for name, ratified, status in contracts:
                flag = "  !" if not ratified or ratified == "—" else "   "
                print(f"{flag} {name:<14}  {status}")

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
    seen_ids: set[str] = {o.id for o in recent_obs} | {o.id for o in upcoming_obs}
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
                rel = format_elapsed(o.logged_at, now)
            tag_str = f" #{o.tag}" if o.tag else ""
            print(f"  {rel:<10}  {o.body}{tag_str}")

    from life.lib.dates import list_dates

    upcoming_dates = [d for d in list_dates() if 0 <= d["days_until"] <= 30]
    if upcoming_dates:
        print("\nDATES:")
        for d in upcoming_dates:
            days = d["days_until"]
            when = "today" if days == 0 else f"in {days}d"
            type_str = f"  [{d['type']}]" if d["type"] != "other" else ""
            print(f"  {when:<10}  {d['name']}{type_str}")

    from life.contacts import get_stale_contacts

    stale = get_stale_contacts()
    if stale:
        print("\nCONTACTS (overdue):")
        for contact, days in stale:
            if days is None:
                label = "never"
            else:
                label = f"{days}d ago"
            print(f"  {contact.name:<12} {label:<10}  (every {contact.cadence_days}d)")

    open_improvements = get_improvements()
    if open_improvements:
        print("\nIMPROVEMENTS:")
        for i in open_improvements[:5]:
            print(f"  [{short('i', i.id)}] {i.body}")

    recent_moods = get_recent_moods(hours=24)
    if recent_moods:
        latest = recent_moods[0]
        rel = format_elapsed(latest.logged_at, datetime.now())
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
        from life.comms.accounts import list_accounts
        from life.comms.drafts import list_pending_drafts

        email_accounts = list_accounts("email")
        if email_accounts:
            from life.comms.services import get_email_adapter

            total_inbox = 0
            flagged_lines: list[str] = []
            for acct in email_accounts:
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

    try:
        from life.comms.messages.telegram import get_history

        # show messages since last operator (inbound) message, not fixed window
        all_recent = get_history(limit=30, hours=48)
        last_operator_idx = None
        for i, m in enumerate(all_recent):
            if m["direction"] == "in":
                last_operator_idx = i
                break
        # show everything since last operator message (inclusive), capped at 15
        if last_operator_idx is not None:
            show = list(reversed(all_recent[: last_operator_idx + 1]))[-15:]
        elif all_recent:
            show = list(reversed(all_recent[:5]))
        else:
            show = []

        if show:
            print("\nTELEGRAM:")
            for m in show:
                direction = "→" if m["direction"] == "out" else "←"
                name = m["peer_name"] or m["peer"]
                ts_val = m["timestamp"]
                ago = int(time.time() - ts_val)
                if ago < 3600:
                    rel = f"{ago // 60}m ago"
                elif ago < 86400:
                    rel = f"{ago // 3600}h ago"
                else:
                    rel = f"{ago // 86400}d ago"
                body = m["body"][:80]
                photo = " 📷" if m.get("image_path") else ""
                print(f"  {rel:<10} {direction} {name}: {body}{photo}")
    except Exception:  # noqa: S110
        pass


def main():
    import sys

    from fncli import dispatch

    init()
    sys.exit(dispatch(["life", "steward", "wake", *sys.argv[1:]]))

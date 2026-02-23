import subprocess
import time
from datetime import date, datetime
from pathlib import Path

from fncli import cli

from ..lib.errors import echo
from . import _rel, get_observations, get_sessions

STEWARD_BIRTHDAY = datetime(2026, 2, 18)


@cli("life steward")
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
    echo(f"STEWARD — day {age_days}  |  {now_local.strftime('%a %d %b %Y  %I:%M%p').lower()}\n")

    tasks = get_tasks()
    all_tasks = get_all_tasks()
    habits = get_habits()
    steward_tasks = [t for t in get_tasks(include_steward=True) if t.steward]
    if steward_tasks:
        echo("STEWARD TASKS:")
        for t in steward_tasks:
            echo(f"  · {t.content}")
        echo("")
    today_date = today()
    snapshot = build_feedback_snapshot(
        all_tasks=all_tasks, pending_tasks=tasks, habits=habits, today=today_date
    )
    echo(render_feedback_headline(snapshot))

    sessions = get_sessions(limit=1)
    if sessions:
        s = sessions[0]
        now = datetime.now()
        secs = (now - s.logged_at).total_seconds()
        rel = _rel(secs)
        echo(f"\nLAST SESSION ({rel}): {s.summary}")

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
        echo("\nOBSERVATIONS:")
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
            echo(f"  {rel:<10}  {o.body}{tag_str}")

    open_improvements = get_improvements()
    if open_improvements:
        echo("\nIMPROVEMENTS:")
        for i in open_improvements[:5]:
            echo(f"  [{i.id}] {i.body}")

    recent_moods = get_recent_moods(hours=24)
    if recent_moods:
        latest = recent_moods[0]
        secs = (datetime.now() - latest.logged_at).total_seconds()
        rel = _rel(secs)
        bar = "█" * latest.score + "░" * (5 - latest.score)
        label_str = f"  {latest.label}" if latest.label else ""
        echo(f"\nMOOD ({rel}): {bar}  {latest.score}/5{label_str}")
        if len(recent_moods) > 1:
            echo(f"  ({len(recent_moods)} entries last 24h)")
    else:
        echo("\nMOOD: none logged — consider asking")

    repos_dir = Path.home() / "life" / "repos"
    if repos_dir.exists():
        subrepos = sorted(p for p in repos_dir.iterdir() if p.is_dir() and (p / ".git").exists())
        if subrepos:
            echo("\nSUBREPOS:")
            now_ts = time.time()
            for repo in subrepos:
                try:
                    result = subprocess.run(
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
                    dirty = "~" if dirty_result.stdout.strip() else " "
                    if result.returncode == 0 and result.stdout.strip():
                        ct_str, _, msg = result.stdout.strip().partition(" ")
                        secs = now_ts - int(ct_str)
                        if secs < 3600:
                            rel = f"{int(secs // 60)}m ago"
                        elif secs < 86400:
                            rel = f"{int(secs // 3600)}h ago"
                        elif secs < 86400 * 7:
                            rel = f"{int(secs // 86400)}d ago"
                        else:
                            rel = f"{int(secs // (86400 * 7))}w ago"
                        echo(f"  {dirty} {repo.name:<16}  {rel:<10}  {msg}")
                    else:
                        echo(f"  {dirty} {repo.name:<16}  (no commits)")
                except Exception:
                    echo(f"    {repo.name:<16}  (error)")

    try:
        from ..comms.accounts import list_accounts
        from ..comms.drafts import list_pending_drafts
        from ..comms.proposals import list_proposals

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
            pending_proposals = list_proposals(status="pending")
            parts = [f"{total_inbox} in inbox"]
            if pending_drafts:
                parts.append(
                    f"{len(pending_drafts)} draft{'s' if len(pending_drafts) != 1 else ''} pending"
                )
            if pending_proposals:
                parts.append(
                    f"{len(pending_proposals)} proposal{'s' if len(pending_proposals) != 1 else ''} to review"
                )
            echo(f"\nCOMMS: {', '.join(parts)}")
            for line in flagged_lines:
                echo(line)
    except Exception as e:
        import os

        if os.environ.get("LIFE_DEBUG"):
            echo(f"\nCOMMS: boot error — {e}")

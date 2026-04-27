import os
from datetime import date, datetime

from fncli import cli

from life.core.errors import NotFoundError
from life.domain.improvements import delete_improvement, get_improvements
from life.lib import ansi
from life.lib.dates import parse_due_date
from life.lib.format import format_elapsed
from life.lib.ids import resolve_prefix, short

from . import add_observation, add_session, delete_observation, get_observations, update_session_summary


@cli("steward")
def sleep(note: str):
    """Write handover summary for the next steward — what happened, what's open, what's next"""
    session_id_env = os.environ.get("STEWARD_SESSION_ID")
    if session_id_env:
        update_session_summary(int(session_id_env), note)
    else:
        add_session(note)
    print("→ summary logged")


@cli("steward", flags={"body": [], "tag": ["-t", "--tag"], "about": ["-a", "--about"]})
def observe(
    body: str | None = None,
    tag: str | None = None,
    about: str | None = None,
):
    """Log a raw observation — things Tyson says that should persist as context"""
    if body is None:
        observations = get_observations(limit=20, tag=tag)
        if not observations:
            print("no observations")
            return
        now = datetime.now()
        for o in observations:
            rel = format_elapsed(o.logged_at, now)
            tag_str = f" #{o.tag}" if o.tag else ""
            print(f"  {ansi.muted('[' + short('o', o.id) + ']')}  {rel:<10}  {o.body}{tag_str}")
        return

    about_date: date | None = None
    if about:
        parsed_str = parse_due_date(about)
        about_date = date.fromisoformat(parsed_str) if parsed_str else None

    add_observation(body, tag=tag, about_date=about_date)
    suffix = f" #{tag}" if tag else ""
    about_str = f" (about {about_date})" if about_date else ""
    print(f"→ {body}{suffix}{about_str}")


@cli("steward")
def rm(prefix: str, hard: bool = False):
    """Remove any steward item by UUID prefix — observations or improvements"""
    obs = resolve_prefix(prefix, get_observations(limit=200))
    if obs:
        delete_observation(obs.id, hard=hard)
        print(f"→ removed: {obs.body[:80]}")
        return

    imp = resolve_prefix(prefix, get_improvements())
    if imp:
        delete_improvement(imp.id, hard=hard)
        print(f"→ removed: {imp.body[:80]}")
        return

    raise NotFoundError(f"no item matching '{prefix}'")

import os
from datetime import date, datetime

from fncli import cli

from life.core.errors import NotFoundError
from life.improvements import delete_improvement, get_improvements
from life.lib import ansi
from life.lib.dates import parse_due_date
from life.lib.format import format_elapsed
from life.lib.ids import resolve_prefix, short

from . import add_observation, close_session, create_session, delete_observation, get_observations


@cli("life")
def sleep(note: str):
    """Write handover summary for the next steward — what happened, what's open, what's next"""
    from life.lib.store import get_db

    db_id_env = os.environ.get("STEWARD_DB_SESSION_ID")
    session_id_env = os.environ.get("STEWARD_SESSION_ID")
    db_id: int | None = None

    if db_id_env:
        db_id = int(db_id_env)
    elif session_id_env:
        try:
            with get_db() as conn:
                row = conn.execute(
                    "SELECT id FROM sessions WHERE claude_session_id = ? ORDER BY id DESC LIMIT 1",
                    (session_id_env,),
                ).fetchone()
            if row:
                db_id = row[0]
        except Exception:
            pass

    if db_id is not None:
        close_session(db_id, summary=note)
    else:
        create_session(note, source="unknown")
    print("→ session closed")


@cli("life", flags={"body": [], "tag": ["-t", "--tag"], "about": ["-a", "--about"]})
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


@cli("life", name="rm-obs")
def rm(prefix: str, hard: bool = False):
    """Remove an observation or improvement by UUID prefix"""
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

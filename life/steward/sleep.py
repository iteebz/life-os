import contextlib
import os
from datetime import date, datetime

from fncli import cli

from life.lib import ansi
from life.lib.dates import parse_due_date
from life.lib.format import format_elapsed
from life.lib.ids import short
from life.lib.store import get_db

from . import (
    add_observation,
    clear_handover,
    close_session,
    create_session,
    get_observations,
)


@cli("life steward", flags={"note": [], "handover": ["-h", "--handover"]})
def sleep(note: str, handover: str | None = None):
    """Close the session — note recaps, --handover points the next steward at the next physical action"""
    db_id_env = os.environ.get("STEWARD_DB_SESSION_ID")
    session_id_env = os.environ.get("STEWARD_SESSION_ID")
    db_id: int | None = None

    if db_id_env:
        db_id = int(db_id_env)
    elif session_id_env:
        with contextlib.suppress(Exception):
            with get_db() as conn:
                row = conn.execute(
                    "SELECT id FROM sessions WHERE claude_session_id = ? ORDER BY id DESC LIMIT 1",
                    (session_id_env,),
                ).fetchone()
            if row:
                db_id = row[0]

    if db_id is not None:
        close_session(db_id, summary=note, handover=handover)
    else:
        create_session(note, source="unknown")
    print("→ session closed" + (f"  handover: {handover}" if handover else ""))


@cli("life steward", flags={"text": [], "done": ["-d", "--done"]})
def handover(text: str | None = None, done: bool = False):
    """Show, set, or mark-done the handover pointer for the next session"""
    from life.steward import latest_handover  # noqa: PLC0415

    if done:
        n = clear_handover()
        print("→ done" if n else "→ no handover to clear")
        return
    if text:
        from life.steward import update_session_handover  # noqa: PLC0415

        update_session_handover(text)
        print(f"→ {text}")
        return
    current = latest_handover()
    print(current or "(no handover)")


@cli("life steward", flags={"body": [], "tag": ["-t", "--tag"], "about": ["-a", "--about"]})
def observe(
    body: str | None = None,
    tag: str | None = None,
    about: str | None = None,
):
    """Log a raw observation — things the human says that should persist as context"""
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

from datetime import datetime

from fncli import cli

from ..lib import ansi
from ..lib.errors import exit_error
from . import _rel, add_observation, add_session, delete_observation, get_observations


@cli("steward")
def close(summary: str):
    """Write session log and close interactive session"""
    add_session(summary)
    print("→ session logged")


@cli("steward", flags={"body": []})
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
            rel = _rel((now - o.logged_at).total_seconds())
            tag_str = f" #{o.tag}" if o.tag else ""
            print(f"  {ansi.muted('[' + o.uuid[:8] + ']')}  {rel:<10}  {o.body}{tag_str}")
        return

    from datetime import date

    from ..lib.dates import parse_due_date

    about_date: date | None = None
    if about:
        parsed_str = parse_due_date(about)
        about_date = date.fromisoformat(parsed_str) if parsed_str else None

    add_observation(body, tag=tag, about_date=about_date)
    suffix = f" #{tag}" if tag else ""
    about_str = f" (about {about_date})" if about_date else ""
    print(f"→ {body}{suffix}{about_str}")


@cli("steward")
def rm(prefix: str):
    """Soft-remove any steward item by UUID prefix — observations or improvements"""
    from ..improvements import delete_improvement, get_improvements
    from . import resolve_prefix

    obs = resolve_prefix(prefix, get_observations(limit=200))
    if obs:
        delete_observation(obs.uuid)
        print(f"→ removed: {obs.body[:80]}")
        return

    imp = resolve_prefix(prefix, get_improvements())
    if imp:
        delete_improvement(imp.uuid)
        print(f"→ removed: {imp.body[:80]}")
        return

    exit_error(f"no item matching '{prefix}'")

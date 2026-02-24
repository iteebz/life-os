from fncli import cli

from ..lib.errors import exit_error
from . import add_observation, add_session, delete_observation, get_observations


@cli("steward")
def close(summary: str):
    """Write session log and close interactive session"""
    add_session(summary)
    print("→ session logged")


@cli("steward")
def observe(
    body: str,
    tag: str | None = None,
    about: str | None = None,
):
    """Log a raw observation — things Tyson says that should persist as context"""
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
def rm(
    query: str | None = None,
):
    """Delete an observation — fuzzy match or latest"""
    observations = get_observations(limit=50)
    if not observations:
        exit_error("no observations to remove")

    if query is None:
        target = observations[0]
    else:
        q = query.lower()
        matches = [o for o in observations if q in o.body.lower()]
        if not matches:
            exit_error(f"no observation matching '{query}'")
        target = matches[0]

    deleted = delete_observation(target.id)
    if deleted:
        print(f"→ removed: {target.body[:80]}")
    else:
        exit_error("delete failed")

from datetime import datetime, timezone

from fncli import cli

from ..lib.errors import echo
from . import _rel, get_sessions


@cli("life steward")
def log(
    limit: int = 10,
):
    """Show recent steward session logs"""
    sessions = get_sessions(limit=limit)
    if not sessions:
        echo("no sessions logged")
        return
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for s in sessions:
        rel = _rel((now - s.logged_at).total_seconds())
        echo(f"{rel:<10}  {s.summary}")

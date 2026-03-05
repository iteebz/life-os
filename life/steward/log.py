from datetime import UTC, datetime

from fncli import cli

from life.lib.format import format_elapsed

from . import get_sessions


@cli("steward")
def log(
    limit: int = 10,
):
    """Show recent steward session logs"""
    sessions = get_sessions(limit=limit)
    if not sessions:
        print("no sessions logged")
        return
    now = datetime.now(UTC).replace(tzinfo=None)
    for s in sessions:
        rel = format_elapsed(s.logged_at, now)
        print(f"{rel:<10}  {s.summary}")

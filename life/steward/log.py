from datetime import UTC, datetime

from fncli import cli

from . import _rel, get_sessions


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
        rel = _rel((now - s.logged_at).total_seconds())
        print(f"{rel:<10}  {s.summary}")

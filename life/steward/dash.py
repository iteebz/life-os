from datetime import datetime

from fncli import cli

from . import _rel, get_observations, get_sessions


@cli("steward")
def dash():
    """Steward dashboard — improvements, patterns, observations, sessions"""
    from ..improvements import get_improvements

    improvements = get_improvements()
    if improvements:
        print("IMPROVEMENTS:")
        for i in improvements:
            print(f"  [{i.id}] {i.body}")
    else:
        print("IMPROVEMENTS: none")

    observations = get_observations(limit=10)
    if observations:
        print("\nRECENT OBSERVATIONS:")
        now = datetime.now()
        for o in observations:
            rel = _rel((now - o.logged_at).total_seconds())
            tag_str = f" #{o.tag}" if o.tag else ""
            print(f"  {rel:<10}  {o.body}{tag_str}")

    sessions = get_sessions(limit=5)
    if sessions:
        print("\nRECENT SESSIONS:")
        now_dt = datetime.now()
        for s in sessions:
            rel = _rel((now_dt - s.logged_at).total_seconds())
            print(f"  {rel:<10}  {s.summary[:90]}")

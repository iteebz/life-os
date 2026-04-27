from datetime import datetime

from fncli import cli

from life.domain.improvements import get_improvements
from life.lib.format import format_elapsed
from life.lib.ids import short

from . import get_observations, get_sessions


@cli("steward")
def dash():
    """Steward dashboard — improvements, patterns, observations, sessions"""
    improvements = get_improvements()
    if improvements:
        print("IMPROVEMENTS:")
        for i in improvements:
            print(f"  [{short('i', i.id)}] {i.body}")
    else:
        print("IMPROVEMENTS: none")

    observations = get_observations(limit=10)
    if observations:
        print("\nRECENT OBSERVATIONS:")
        now = datetime.now()
        for o in observations:
            rel = format_elapsed(o.logged_at, now)
            tag_str = f" #{o.tag}" if o.tag else ""
            print(f"  {rel:<10}  {o.body}{tag_str}")

    sessions = get_sessions(limit=5)
    if sessions:
        print("\nRECENT LIVES:")
        now_dt = datetime.now()
        for s in sessions:
            rel = format_elapsed(s.logged_at, now_dt)
            print(f"  {rel:<10}  {s.summary[:90]}")

import sys

import fncli

from life.store.migrations import init

from . import __all__ as _  # registers all steward submodules with fncli  # noqa: F401


RESUME_WINDOW_SECONDS = 3600


def _smart_resume() -> int:
    """Resume recent session if within window, otherwise start new."""
    from datetime import datetime

    from .chat import chat, continue_session

    sessions = __import__("life.steward", fromlist=["get_sessions"]).get_sessions(limit=5)
    resumable = [s for s in sessions if s.claude_session_id]

    if resumable:
        latest = resumable[0]
        last_touch = latest.logged_at
        if latest.follow_ups:
            last_touch = max(last_touch, datetime.fromisoformat(latest.follow_ups[-1]))
        age = (datetime.now() - last_touch).total_seconds()
        if age < RESUME_WINDOW_SECONDS:
            return continue_session() or 0

    return chat() or 0


def main():
    init()
    args = sys.argv[1:]
    if not args:
        sys.exit(_smart_resume())
    if args[0] in ("-h", "--help"):
        fncli.try_dispatch(["steward", "--help"])
        sys.exit(0)
    # pass flags through to chat for bare flag invocations (--opus, --raw, -m)
    if args[0].startswith("-") and args[0] not in ("-h", "--help"):
        sys.exit(fncli.dispatch(["steward", "chat", *args]))
    sys.exit(fncli.dispatch(["steward", *args]))

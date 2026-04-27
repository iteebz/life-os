import sys
from datetime import datetime
from pathlib import Path

import fncli

from .core.errors import LifeError
from .store import migrations as db

_STEWARD_CHAT_FLAGS = {"--opus", "-m", "--model", "-n", "--name", "--raw"}
_RESUME_WINDOW_SECONDS = 3600


def _smart_resume() -> int:
    from .steward import get_sessions
    from .steward.chat import chat, continue_session

    sessions = get_sessions(limit=5)
    resumable = [s for s in sessions if s.claude_session_id]

    if resumable:
        latest = resumable[0]
        last_touch = latest.logged_at
        if latest.follow_ups:
            last_touch = max(last_touch, datetime.fromisoformat(latest.follow_ups[-1]))
        if (datetime.now() - last_touch).total_seconds() < _RESUME_WINDOW_SECONDS:
            return continue_session() or 0

    return chat() or 0


def main():
    db.init()
    fncli.autodiscover(Path(__file__).parent, "life")
    fncli.alias_namespace("steward", "life steward")

    user_args = sys.argv[1:]
    if not user_args or user_args == ["-v"] or user_args == ["--verbose"]:
        from .dash import dashboard  # noqa: PLC0415 — circular: cli→dash→habit→tag→resolve→task→tag
        dashboard()
        return
    # life steward (bare) → smart resume
    if user_args == ["steward"]:
        sys.exit(_smart_resume())
    # life steward --opus → life steward chat --opus
    if len(user_args) >= 2 and user_args[0] == "steward" and user_args[1] in _STEWARD_CHAT_FLAGS:
        user_args = ["steward", "chat", *user_args[1:]]
    argv = ["life", *user_args]
    try:
        code = fncli.dispatch(argv)
    except LifeError as e:
        sys.stderr.write(f"{e}\n")
        sys.exit(1)
    sys.exit(code)


if __name__ == "__main__":
    main()

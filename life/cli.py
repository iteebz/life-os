import os
import sys
from datetime import datetime
from pathlib import Path

import fncli

from .core.errors import LifeError
from .steward import get_sessions
from .steward.chat import DEFAULT_MODEL, _launch, chat
from .store import migrations as db

_STEWARD_CHAT_FLAGS = {"--opus", "--sonnet", "-m", "--model", "-n", "--name", "--raw"}
_RESUME_WINDOW_SECONDS = 3600


def _smart_resume() -> int:
    sessions = get_sessions(limit=5)
    resumable = [s for s in sessions if s.claude_session_id and s.state in ("active", "idle")]

    if resumable:
        target = resumable[0]
        last_touch = target.last_active_at or target.started_at or target.logged_at
        if (datetime.now() - last_touch).total_seconds() < _RESUME_WINDOW_SECONDS:
            sid = target.claude_session_id
            assert sid is not None  # noqa: S101 — guaranteed by resumable filter
            m = target.model or DEFAULT_MODEL
            source = os.environ.get("STEWARD_SOURCE", "cli")
            print(f"resuming {target.id} → {sid[:8]}  model={m}  source={source}")
            return _launch(m, sid, name=target.name, resume=True, source=source, db_session_id=target.id)

    return chat() or 0


def main():
    db.init()
    fncli.autodiscover(Path(__file__).parent, "life")

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

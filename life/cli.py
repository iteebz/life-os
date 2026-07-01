import os
import sys
from datetime import datetime
from pathlib import Path

import fncli

from lifeos.core.errors import LifeError
from lifeos.core.store import migrations as db
from lifeos.steward import get_sessions
from lifeos.steward.chat import DEFAULT_MODEL, _launch, chat

_STEWARD_CHAT_FLAGS = {"--opus", "--sonnet", "-m", "--model", "-n", "--name", "--raw"}
_RESUME_WINDOW_SECONDS = 3600


def _smart_resume() -> int:
    sessions = get_sessions(limit=5)
    resumable = [s for s in sessions if s.provider_session_id and s.state in ("active", "idle")]

    if resumable:
        target = resumable[0]
        last_touch = target.last_active_at or target.started_at or target.logged_at
        if (datetime.now() - last_touch).total_seconds() < _RESUME_WINDOW_SECONDS:
            sid = target.provider_session_id
            assert sid is not None
            m = target.model or DEFAULT_MODEL
            source = os.environ.get("STEWARD_SOURCE", "cli")
            print(f"resuming {target.id} → {sid[:8]}  model={m}  source={source}")
            return _launch(m, sid, name=target.name, resume=True, source=source, db_session_id=target.id)

    return chat() or 0


def _watch() -> None:
    import time

    from rich.console import Console
    from rich.live import Live
    from rich.text import Text

    from lifeos.core.lib import clock
    from lifeos.core.lib.ansi import theme

    from .dash import get_habits, get_tasks, get_today_breakdown, get_today_completed
    from .task.render import render_dashboard

    def _render() -> Text:
        items = get_tasks() + get_habits()
        body = render_dashboard(items, get_today_breakdown(), today_items=get_today_completed())
        stamp = f"{theme.muted}updated {clock.now().strftime('%H:%M:%S')}{theme.reset}\n"
        return Text.from_ansi(body + stamp)

    console = Console()
    with Live(_render(), console=console, refresh_per_second=4, screen=False, transient=False) as live:
        try:
            while True:
                time.sleep(1)
                live.update(_render())
        except KeyboardInterrupt:
            pass


def main():
    db.init()
    fncli.autodiscover(Path(__file__).parent, "life")

    user_args = sys.argv[1:]
    if not user_args or user_args == ["-v"] or user_args == ["--verbose"]:
        from .dash import get_habits, get_tasks, get_today_breakdown, get_today_completed
        from .task.render import render_dashboard

        items = get_tasks() + get_habits()
        print(render_dashboard(items, get_today_breakdown(), today_items=get_today_completed()))
        return
    if user_args == ["-w"]:
        _watch()
        return
    # natural-language aliases
    aliases = {"tasks": "task", "habits": "habit"}
    if user_args[0] in aliases:
        user_args = [aliases[user_args[0]], *user_args[1:]]
    # life steward (bare) → new session
    if user_args == ["steward"]:
        from lifeos.steward.chat import chat

        sys.exit(chat() or 0)
    # life steward continue / life steward chat → smart resume
    if len(user_args) == 2 and user_args[0] == "steward" and user_args[1] in ("continue", "chat"):
        sys.exit(_smart_resume())
    # life steward --opus → life steward chat --opus
    if len(user_args) >= 2 and user_args[0] == "steward" and user_args[1] in _STEWARD_CHAT_FLAGS:
        user_args = ["steward", "chat", *user_args[1:]]
    # life t/abc123, life o/abc, life i/abc, life s/201 → resolve ref directly
    if len(user_args) == 1 and "/" in user_args[0] and not user_args[0].startswith("-"):
        from .ref import _resolve_and_print

        if not _resolve_and_print(user_args[0]):
            sys.stderr.write(f"nothing found: '{user_args[0]}'\n")
            sys.exit(1)
        return
    if user_args[0] == "hook":
        from .hooks import main as hook_main

        sys.argv = ["life", *user_args]
        hook_main()
        return
    argv = ["life", *user_args]
    try:
        code = fncli.dispatch(argv)
    except LifeError as e:
        sys.stderr.write(f"{e}\n")
        sys.exit(1)
    sys.exit(code)


if __name__ == "__main__":
    main()

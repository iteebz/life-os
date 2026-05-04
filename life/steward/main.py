import os
import sys
from pathlib import Path

import fncli

from life.hook import main as hook_main
from life.store.migrations import init

_SESSION_FLAGS = {"--opus", "--sonnet"}


def main():
    args = sys.argv[1:]
    # fast path — hooks fire on every tool call, skip fncli overhead
    if args and args[0] == "hook":
        sys.argv = ["steward-hook", *args[1:]]
        hook_main()
        return
    init()
    fncli.autodiscover(Path(__file__).resolve().parent.parent, "life")
    fncli.alias_namespace("life steward", "steward")
    # steward (bare) → new session
    if not args:
        from life.steward.chat import chat  # noqa: PLC0415

        sys.exit(chat() or 0)
    # steward continue / steward chat → smart resume
    if args[0] in ("continue", "chat") and len(args) == 1:
        from life.cli import _smart_resume  # noqa: PLC0415

        sys.exit(_smart_resume())
    # steward --opus / --sonnet → new session with that model (unless already in session)
    if args[0] in _SESSION_FLAGS and os.environ.get("STEWARD_MODE") != "chat":
        args = ["chat", *args]
    sys.exit(fncli.dispatch(["steward", *args]))

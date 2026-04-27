import sys

import fncli

from life.hook import main as hook_main
from life.store.migrations import init

from . import __all__ as _  # registers all steward submodules with fncli  # noqa: F401


def main():
    args = sys.argv[1:]
    # fast path — hooks fire on every tool call, skip fncli overhead
    if args and args[0] == "hook":
        sys.argv = ["steward-hook", *args[1:]]
        hook_main()
        return
    init()
    if not args or args[0] in ("-h", "--help"):
        fncli.try_dispatch(["steward", "--help"])
        sys.exit(0)
    sys.exit(fncli.dispatch(["steward", *args]))

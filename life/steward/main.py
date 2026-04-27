import sys

import fncli

from life.store.migrations import init

from . import __all__ as _  # registers all steward submodules with fncli  # noqa: F401

_CHAT_FLAGS = {"--opus", "-m", "--model", "-n", "--name", "--raw"}


def main():
    init()
    args = sys.argv[1:]
    if not args or args == ["-h"] or args == ["--help"]:
        fncli.try_dispatch(["steward", "--help"])
        sys.exit(0)
    if args[0].startswith("-") and args[0] in _CHAT_FLAGS:
        args = ["chat", *args]
    sys.exit(fncli.dispatch(["steward", *args]))

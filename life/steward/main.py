import sys

import fncli

from life.store.migrations import init

from . import __all__ as _  # registers all steward submodules with fncli  # noqa: F401


def main():
    init()
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        fncli.try_dispatch(["steward", "--help"])
        sys.exit(0)
    sys.exit(fncli.dispatch(["steward", *args]))

import sys

import fncli

from life.db import init

from . import __all__ as _  # registers all steward submodules with fncli  # noqa: F401


def main():
    init()
    sys.exit(fncli.dispatch(["steward", *sys.argv[1:]]))

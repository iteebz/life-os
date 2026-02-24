import sys

from ..db import init
from . import __all__ as _  # registers all steward submodules with fncli  # noqa: F401


def main():
    import fncli

    init()
    sys.exit(fncli.dispatch(["steward", *sys.argv[1:]]))

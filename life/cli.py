import sys
from pathlib import Path

import fncli

from . import db


def main():
    db.init()
    fncli.autodiscover(Path(__file__).parent, "life")

    user_args = sys.argv[1:]
    if not user_args or user_args == ["-v"] or user_args == ["--verbose"]:
        from .dash import dashboard

        dashboard(verbose="--verbose" in user_args or "-v" in user_args)
        return
    argv = ["life", *user_args]
    code = fncli.dispatch(argv)
    sys.exit(code)


if __name__ == "__main__":
    main()

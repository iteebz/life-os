import sys
from pathlib import Path

import fncli

from . import db
from .core.errors import LifeError


def main():
    db.init()
    fncli.autodiscover(Path(__file__).parent, "life")

    user_args = sys.argv[1:]
    if not user_args or user_args == ["-v"] or user_args == ["--verbose"]:
        from .dash import dashboard

        dashboard()
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

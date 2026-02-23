import sys

from . import achievements as _achievements
from . import add as _add
from . import backup as _backup
from . import daemon as _daemon
from . import dash as _dash
from . import dates as _dates
from . import db
from . import habits as _habits
from . import interventions as _interventions
from . import items as _items
from . import mood as _mood
from . import patterns as _patterns
from . import steward as _steward
from . import tag as _tags
from . import tasks as _tasks

_ = (
    _backup,
    _daemon,
    _steward,
    _achievements,
    _add,
    _dash,
    _dates,
    _interventions,
    _items,
    _mood,
    _patterns,
    _tasks,
    _habits,
    _tags,
)


def main():
    db.init()
    from fncli import dispatch

    user_args = sys.argv[1:]
    if not user_args or user_args == ["-v"] or user_args == ["--verbose"]:
        from .dash import dashboard

        dashboard(verbose="--verbose" in user_args or "-v" in user_args)
        return
    argv = ["life", *user_args]
    code = dispatch(argv)
    sys.exit(code)


if __name__ == "__main__":
    main()

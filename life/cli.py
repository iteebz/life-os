import sys

from . import accounts as _accounts
from . import achievements as _achievements
from . import add as _add
from . import daemon as _daemon
from . import dash as _dash
from . import dates as _dates
from . import db
from . import email as _email
from . import habits as _habits
from . import install as _install
from . import interventions as _interventions
from . import items as _items
from . import messaging as _messaging
from . import mood as _mood
from . import patterns as _patterns
from . import signal as _signal
from . import steward as _steward
from . import tag as _tags
from . import tasks as _tasks

_ = (
    _daemon,
    _install,
    _steward,
    _accounts,
    _achievements,
    _add,
    _dash,
    _dates,
    _email,
    _interventions,
    _items,
    _mood,
    _patterns,
    _messaging,
    _signal,
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

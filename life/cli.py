import sys
from pathlib import Path

import fncli

from .store import migrations as db
from .core.errors import LifeError

_STEWARD_CHAT_FLAGS = {"--opus", "-m", "--model", "-n", "--name", "--raw"}


def main():
    db.init()
    fncli.autodiscover(Path(__file__).parent, "life")
    fncli.alias_namespace("steward", "life steward")

    user_args = sys.argv[1:]
    if not user_args or user_args == ["-v"] or user_args == ["--verbose"]:
        from .dash import dashboard  # noqa: PLC0415 — circular: cli→dash→habit→tag→resolve→task→tag
        dashboard()
        return
    # life steward [--opus] → smart resume: continue if recent, else new chat
    if user_args[0] == "steward" and (len(user_args) == 1 or (len(user_args) >= 2 and user_args[1] in _STEWARD_CHAT_FLAGS)):
        user_args = ["steward", "chat", *user_args[1:]]
    argv = ["life", *user_args]
    try:
        code = fncli.dispatch(argv)
    except LifeError as e:
        sys.stderr.write(f"{e}\n")
        sys.exit(1)
    sys.exit(code)


if __name__ == "__main__":
    main()

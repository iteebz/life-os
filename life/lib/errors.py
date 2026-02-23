import sys
from typing import NoReturn

__all__ = ["exit_error"]


def exit_error(message: str, code: int = 1) -> NoReturn:
    sys.stderr.write(message + "\n")
    sys.exit(code)

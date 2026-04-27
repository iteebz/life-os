import sys

import fncli

import life.accounts  # pyright: ignore[reportUnusedImport]
import life.comms.messages.signal  # pyright: ignore[reportUnusedImport]
import life.email  # noqa: F401  # pyright: ignore[reportUnusedImport]


def main():
    fncli.alias_namespace("life comms", "comms")
    sys.exit(fncli.dispatch(["comms", *sys.argv[1:]]))

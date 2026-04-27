import sys

import fncli

import life.comms.accounts_cli  # pyright: ignore[reportUnusedImport]
import life.comms.email_cli  # pyright: ignore[reportUnusedImport]
import life.comms.messages.signal  # pyright: ignore[reportUnusedImport]


def main():
    fncli.alias_namespace("life comms", "comms")
    sys.exit(fncli.dispatch(["comms", *sys.argv[1:]]))

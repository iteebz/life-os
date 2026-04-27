import sys

import life.accounts as _accounts
import life.comms.messages.signal as _signal
import life.email as _email

_ = (_accounts, _email, _signal)


def main():
    import fncli

    fncli.alias_namespace("life comms", "comms")
    sys.exit(fncli.dispatch(["comms", *sys.argv[1:]]))

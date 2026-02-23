import sys

import life.accounts as _accounts
import life.email as _email
import life.messaging as _messaging
import life.signal as _signal

_ = (_accounts, _email, _messaging, _signal)


def main():
    import fncli

    fncli.alias_namespace("life comms", "comms")
    sys.exit(fncli.dispatch(["comms", *sys.argv[1:]]))

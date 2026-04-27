"""Steward wake — print full life snapshot for boot context."""

import sys

import fncli
from fncli import cli

from life.ctx.assemble import build_wake
from life.store.migrations import init


@cli("life steward")
def wake():
    """Load life state and emit sitrep for interactive session start"""
    print(build_wake())


def main():
    init()
    sys.exit(fncli.dispatch(["life", "steward", "wake", *sys.argv[1:]]))

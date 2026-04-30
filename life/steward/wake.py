"""Steward wake — print full life snapshot for boot context."""

import sys

import fncli
from fncli import cli

from life.store.migrations import init


@cli("life steward")
def wake():
    """Load life state and emit sitrep for interactive session start"""
    from life.ctx.assemble import build_wake  # noqa: PLC0415, I001 — cycle: steward.wake→ctx.assemble→ctx.sections→life.steward→steward.wake

    print(build_wake())


def main():
    init()
    sys.exit(fncli.dispatch(["life", "steward", "wake", *sys.argv[1:]]))

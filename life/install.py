"""life install — register launchd daemon for always-on operation."""

from fncli import cli

from life.lib.errors import echo
from life.lib.install import install_daemon


@cli("life", name="install", description="register launchd daemon for always-on operation")
def main() -> None:
    registered = install_daemon()
    echo("  daemon registered" if registered else "  daemon up to date")

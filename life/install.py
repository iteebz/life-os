"""life install — register launchd daemon for always-on operation."""

from fncli import cli

from life.lib.install import install_daemon


@cli("life", name="install", description="register launchd daemon for always-on operation")
def main() -> None:
    registered = install_daemon()
    print("  daemon registered" if registered else "  daemon up to date")  # noqa: T201

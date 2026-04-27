"""Steward inbox — check for messages received while idle."""

from fncli import cli

from life.daemon.inbound import pending_inbox


@cli("steward")
def inbox():
    """Check for messages received while steward was idle"""
    content = pending_inbox()
    if content:
        print(content)
    else:
        print("no pending messages")

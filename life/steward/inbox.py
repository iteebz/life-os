"""Steward inbox — peek messages received while idle."""

from fncli import cli

from life.comms.events import peek_inbox


@cli("life steward")
def inbox():
    """Check for messages received while steward was idle"""
    rows = peek_inbox()
    if not rows:
        print("no pending messages")
        return
    for _id, ch, name, body, _ts in rows:
        print(f"[{ch}] {name or '?'}: {(body or '')[:200]}")

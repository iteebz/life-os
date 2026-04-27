"""Legacy messaging — commands moved to life/messages.py and life/tg.py.

Kept for receive polling used by the daemon.
"""

from .comms.messages import signal as _signal
from .comms.messages import telegram as _telegram


def poll_incoming(timeout: int = 5) -> list[dict]:
    """Poll all channels for new messages. Used by daemon."""
    msgs: list[dict] = [
        {"channel": "signal", "from": m.get("from_name") or m.get("from", "?"), "body": m["body"]}
        for m in _signal.receive(timeout=timeout)
    ]
    msgs.extend(
        {"channel": "telegram", "from": m["from_name"], "body": m["body"]}
        for m in _telegram.poll(timeout=timeout)
    )
    return msgs

"""Shim — all signal logic lives in life.signal."""

from life.signal import (
    get_conversations,
    get_message,
    get_messages,
    list_accounts,
    list_groups,
    mark_read,
    receive,
    send_group,
    test_connection,
)
from life.signal import (
    link_device as link,
)
from life.signal import (
    list_contacts_for as list_contacts,
)
from life.signal import (
    reply_to as reply,
)
from life.signal import (
    send_to as send,
)

__all__ = [
    "get_conversations",
    "get_message",
    "get_messages",
    "link",
    "list_accounts",
    "list_contacts",
    "list_groups",
    "mark_read",
    "receive",
    "reply",
    "send",
    "send_group",
    "test_connection",
]

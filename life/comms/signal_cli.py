from datetime import datetime

from fncli import cli

from lifeos.core.comms.messages.signal import (
    default_account,
    get_conversations,
    get_messages,
    list_accounts,
    list_contacts_for,
    list_groups,
    receive,
    reply_to,
    resolve_contact,
    send,
)
from lifeos.core.errors import LifeError, NotFoundError


@cli("life signal", name="send")
def send_cmd(
    recipient: str,
    message: str,
    attachment: str | None = None,
):
    """Send a Signal message to a contact or number"""
    number = resolve_contact(recipient)
    success, result = send(number, message, attachment=attachment)
    if success:
        display = recipient if number == recipient else f"{recipient} ({number})"
        print(f"sent → {display}")
    else:
        raise LifeError(f"failed: {result}")


@cli("life signal", name="check")
def check(timeout: int = 5):
    """Pull and display recent Signal messages"""
    messages = receive(timeout=timeout)
    if not messages:
        print("no new messages")
        return
    for msg in messages:
        sender = msg.get("from_name") or msg.get("from", "?")
        print(f"{sender}: {msg['body']}")


@cli("life signal", name="receive")
def receive_cmd(timeout: int = 5):
    """Receive and store Signal messages"""
    phone = default_account()
    if not phone:
        raise NotFoundError("no Signal account registered")
    msgs = receive(timeout=timeout, phone=phone, store=True)
    if not msgs:
        print("no new messages")
        return
    print(f"received {len(msgs)} message(s)")
    for msg in msgs:
        sender = msg.get("from_name") or msg.get("from", "?")
        print(f"  {sender}: {msg['body']}")


@cli("life signal", name="inbox")
def signal_inbox():
    """Show Signal conversations"""
    phone = default_account()
    if not phone:
        raise NotFoundError("no Signal account registered")
    conversations = get_conversations(phone)
    if not conversations:
        print("no conversations — run `life signal receive` first")
        return
    for c in conversations:
        name = c["sender_name"] or c["sender_phone"]
        unread = f" ({c['unread_count']} unread)" if c["unread_count"] else ""
        phone_col = c["sender_phone"] or ""
        print(f"  {phone_col:16} | {name:20} | {c['message_count']} msgs{unread}")


@cli("life signal", name="history")
def signal_history(contact: str, limit: int = 20):
    """Show message history with a contact"""
    phone = default_account()
    if not phone:
        raise NotFoundError("no Signal account registered")
    msgs = get_messages(phone=phone, sender=contact, limit=limit)
    if not msgs:
        print(f"no messages from {contact}")
        return
    for msg in reversed(msgs):
        sender = msg.get("peer_name") or msg.get("peer", "?")
        ts = datetime.fromtimestamp(msg["timestamp"] / 1000).strftime("%d/%m %H:%M")
        mid = msg["id"][:8] if msg.get("id") else ""
        print(f"{mid} [{ts}] {sender}: {msg['body']}")


@cli("life signal", name="reply")
def reply_cmd(message_id: str, message: str):
    """Reply to a Signal message"""
    phone = default_account()
    if not phone:
        raise NotFoundError("no Signal account registered")
    success, err, original = reply_to(phone, message_id, message)
    if success and original:
        sender = original.get("peer_name") or original.get("peer", "?")
        print(f"replied to {sender}")
    else:
        raise LifeError(f"failed: {err}")


@cli("life signal", name="status")
def status():
    """Show registered Signal accounts"""
    accounts = list_accounts()
    if not accounts:
        print("no Signal accounts — run: signal-cli link")
        return
    for account in accounts:
        print(account)


@cli("life signal", name="contacts")
def contacts_cmd():
    """List Signal contacts"""
    phone = default_account()
    if not phone:
        raise NotFoundError("no Signal account registered")
    contacts = list_contacts_for(phone)
    if not contacts:
        print("no contacts")
        return
    for c in contacts:
        print(f"  {c['number']:20} {c.get('name', '')}")


@cli("life signal", name="groups")
def groups_cmd():
    """List Signal groups"""
    phone = default_account()
    if not phone:
        raise NotFoundError("no Signal account registered")
    groups = list_groups(phone)
    if not groups:
        print("no groups")
        return
    for g in groups:
        print(f"  {g['id'][:16]} | {g['name']}")

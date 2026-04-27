from fncli import cli

from .comms.messages import signal as _signal
from .comms.messages import telegram as _telegram
from .core.errors import LifeError, ValidationError


def _default_channel(name: str) -> str | None:
    if _signal.resolve_contact(name) != name:
        return "signal"
    if _telegram.resolve_chat_id(name) is not None:
        return "telegram"
    return None


def _send_signal(recipient: str, message: str) -> tuple[bool, str, str]:
    number = _signal.resolve_contact(recipient)
    success, result = _signal.send(number, message)
    display = recipient if number == recipient else f"{recipient} ({number})"
    return success, result, display


def _send_telegram(recipient: str, message: str) -> tuple[bool, str, str]:
    if not _telegram._token():
        return False, "telegram not configured — run: life comms telegram setup <token>", recipient
    chat_id = _telegram.resolve_chat_id(recipient)
    if chat_id is None:
        return False, f"can't resolve '{recipient}' for telegram", recipient
    success, result = _telegram.send(chat_id, message)
    display = recipient if str(chat_id) == recipient else f"{recipient} ({chat_id})"
    return success, result, display


@cli("life comms message", name="send")
def send_cmd(recipient: str, message: str, signal: bool = False, telegram: bool = False):
    """Send a message via Signal or Telegram"""
    if signal and telegram:
        raise ValidationError("pick one: --signal or --telegram")

    if signal:
        channel = "signal"
    elif telegram:
        channel = "telegram"
    else:
        channel = _default_channel(recipient)
        if not channel:
            raise ValidationError(
                f"can't resolve '{recipient}' — add signal: or telegram: "
                "to their people profile, or pass --signal/--telegram"
            )

    if channel == "signal":
        success, result, display = _send_signal(recipient, message)
    else:
        success, result, display = _send_telegram(recipient, message)

    if success:
        print(f"sent → {display} ({channel})")
    else:
        raise LifeError(f"failed: {result}")


@cli("life comms message", name="receive")
def receive_cmd(timeout: int = 5, signal: bool = False, telegram: bool = False):
    """Poll for new messages"""
    both = not signal and not telegram
    total = 0

    if both or signal:
        msgs = _signal.receive(timeout=timeout)
        for msg in msgs:
            sender = msg.get("from_name") or msg.get("from", "?")
            print(f"  [signal] {sender}: {msg['body']}")
            total += 1

    if both or telegram:
        msgs = _telegram.poll(timeout=timeout)
        for msg in msgs:
            print(f"  [telegram] {msg['from_name']}: {msg['body']}")
            total += 1

    if total == 0:
        print("no new messages")
    else:
        print(f"{total} message(s)")


@cli("life comms telegram", name="auth")
def telegram_auth_cmd(api_id: int, api_hash: str):
    """Store Telegram user API credentials (from my.telegram.org)"""
    from .comms.messages.telegram_sync import save_credentials
    save_credentials(api_id, api_hash)
    print(f"saved — api_id={api_id}. run: life comms telegram sync <chat> to pull history")


@cli("life comms telegram", name="sync", flags={"limit": ["-n"], "full": ["--full"]})
def telegram_sync_cmd(chat: str, limit: int = 0, full: bool = False):
    """Sync telegram chat history into messages DB"""
    from .comms.messages.telegram_sync import sync
    chat_ref: str | int = int(chat) if chat.lstrip("-").isdigit() else chat
    n = sync(chat_ref, limit=limit or None, full=full)
    print(f"synced {n} messages from {chat}")


@cli("life comms telegram", name="history")
def telegram_history_cmd(limit: int = 20, hours: int = 0, chat: str = ""):
    """Show stored telegram message history"""
    chat_id = _telegram.resolve_chat_id(chat) if chat else None
    msgs = _telegram.get_history(chat_id=chat_id, limit=limit, hours=hours or None)
    if not msgs:
        print("no telegram messages stored")
        return
    for m in reversed(msgs):
        direction = "→" if m["direction"] == "out" else "←"
        name = m["peer_name"] or m["peer"]
        import time
        ts = time.strftime("%m/%d %H:%M", time.localtime(m["timestamp"]))
        body = m["body"][:120]
        print(f"  {ts} {direction} {name}: {body}")


@cli("life comms telegram", name="setup")
def telegram_setup_cmd(token: str):
    """Store Telegram bot token"""
    success, result = _telegram.setup(token)
    if success:
        print(f"connected — {result}")
    else:
        print(result)

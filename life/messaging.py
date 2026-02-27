from fncli import cli

from . import signal as _signal
from . import telegram as _telegram
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
                f"can't resolve '{recipient}' — add signal: or telegram: to their people profile, or pass --signal/--telegram"
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


@cli("life comms telegram", name="setup")
def telegram_setup_cmd(token: str):
    """Store Telegram bot token"""
    success, result = _telegram.setup(token)
    if success:
        print(f"connected — {result}")
    else:
        print(result)

from fncli import cli

from . import signal as _signal
from . import telegram as _telegram
from .lib.errors import echo, exit_error


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
        return False, "telegram not configured — run: life telegram setup <token>", recipient
    chat_id = _telegram.resolve_chat_id(recipient)
    if chat_id is None:
        return False, f"can't resolve '{recipient}' for telegram", recipient
    success, result = _telegram.send(chat_id, message)
    display = recipient if str(chat_id) == recipient else f"{recipient} ({chat_id})"
    return success, result, display


@cli("life message", name="send")
def send_cmd(recipient: str, message: str, signal: bool = False, telegram: bool = False):
    """Send a message via Signal or Telegram"""
    if signal and telegram:
        exit_error("pick one: --signal or --telegram")

    if signal:
        channel = "signal"
    elif telegram:
        channel = "telegram"
    else:
        channel = _default_channel(recipient)
        if not channel:
            exit_error(
                f"can't resolve '{recipient}' — add signal: or telegram: to their people profile, or pass --signal/--telegram"
            )

    if channel == "signal":
        success, result, display = _send_signal(recipient, message)
    else:
        success, result, display = _send_telegram(recipient, message)

    if success:
        echo(f"sent → {display} ({channel})")
    else:
        exit_error(f"failed: {result}")


@cli("life message", name="receive")
def receive_cmd(timeout: int = 5, signal: bool = False, telegram: bool = False):
    """Poll for new messages"""
    both = not signal and not telegram
    total = 0

    if both or signal:
        msgs = _signal.receive(timeout=timeout)
        for msg in msgs:
            sender = msg.get("from_name") or msg.get("from", "?")
            echo(f"  [signal] {sender}: {msg['body']}")
            total += 1

    if both or telegram:
        msgs = _telegram.poll(timeout=timeout)
        for msg in msgs:
            echo(f"  [telegram] {msg['from_name']}: {msg['body']}")
            total += 1

    if total == 0:
        echo("no new messages")
    else:
        echo(f"{total} message(s)")


@cli("life telegram", name="setup")
def telegram_setup_cmd(token: str):
    """Store Telegram bot token"""
    success, result = _telegram.setup(token)
    if success:
        echo(f"connected — {result}")
    else:
        echo(result)

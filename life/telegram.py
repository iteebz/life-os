import contextlib
from typing import Any

import keyring
import requests

from .db import get_db
from .lib.resolve import resolve_people_field

SERVICE = "life-cli-telegram"
TOKEN_KEY = "bot_token"  # noqa: S105
API = "https://api.telegram.org/bot{token}"

_cached_token: str | None = None
_cached_update_id: int | None = None


def _token() -> str | None:
    global _cached_token
    if _cached_token is None:
        _cached_token = keyring.get_password(SERVICE, TOKEN_KEY)
    return _cached_token


def _api(method: str, token: str, **kwargs: Any) -> dict[str, Any]:
    url = f"{API.format(token=token)}/{method}"
    resp = requests.post(url, json=kwargs, timeout=30)
    resp.raise_for_status()
    return resp.json()


def resolve_chat_id(name: str) -> int | None:
    if name.lstrip("-").isdigit():
        return int(name)
    result = resolve_people_field(name, "telegram")
    return int(result) if result else None


def send(chat_id: int, message: str, token: str | None = None) -> tuple[bool, str]:
    tok = token or _token()
    if not tok:
        return False, "no telegram bot token — run: life telegram setup <token>"
    try:
        result = _api("sendMessage", tok, chat_id=chat_id, text=message)
        if result.get("ok"):
            msg = result.get("result", {})
            _store_outgoing(chat_id, message, msg.get("message_id", 0), msg.get("date", 0))
            return True, "sent"
        return False, result.get("description", "send failed")
    except requests.RequestException as e:
        return False, str(e)


def _store_outgoing(chat_id: int, body: str, message_id: int, ts: int) -> None:
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO messages (id, channel, direction, peer, peer_name, body, timestamp, success) VALUES (?, 'telegram', 'out', ?, 'steward', ?, ?, 1)",
                (f"tg-{message_id}", str(chat_id), body, ts),
            )
    except Exception:  # noqa: S110
        pass


def poll(timeout: int = 5, token: str | None = None) -> list[dict[str, Any]]:
    tok = token or _token()
    if not tok:
        return []

    last = _last_update_id()
    offset = last + 1 if last else None
    params: dict[str, Any] = {"timeout": timeout, "allowed_updates": ["message"]}
    if offset:
        params["offset"] = offset

    try:
        result = _api("getUpdates", tok, **params)
    except requests.RequestException:
        return []

    if not result.get("ok"):
        return []

    messages = []
    for update in result.get("result", []):
        _save_update_id(update["update_id"])
        msg = update.get("message")
        if not msg or not msg.get("text"):
            continue
        sender = msg.get("from", {})
        last_name = sender.get("last_name", "")
        parsed = {
            "id": msg["message_id"],
            "chat_id": msg["chat"]["id"],
            "from_id": sender.get("id"),
            "from_name": (
                sender.get("first_name", "") + (" " + last_name if last_name else "")
            ).strip(),
            "body": msg["text"],
            "timestamp": msg["date"],
        }
        messages.append(parsed)
        _store_incoming(parsed)

    return messages


def _store_incoming(msg: dict[str, Any]) -> None:
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO messages (id, channel, direction, peer, peer_name, body, timestamp) VALUES (?, 'telegram', 'in', ?, ?, ?, ?)",
                (
                    f"tg-{msg['id']}",
                    str(msg["chat_id"]),
                    msg["from_name"],
                    msg["body"],
                    msg["timestamp"],
                ),
            )
    except Exception:  # noqa: S110
        pass


def _last_update_id() -> int:
    global _cached_update_id
    if _cached_update_id is None:
        try:
            val = keyring.get_password(SERVICE, "last_update_id")
            _cached_update_id = int(val) if val else 0
        except Exception:
            _cached_update_id = 0
    return _cached_update_id


def _save_update_id(update_id: int) -> None:
    global _cached_update_id
    _cached_update_id = update_id
    with contextlib.suppress(Exception):
        keyring.set_password(SERVICE, "last_update_id", str(update_id))


def setup(token: str) -> tuple[bool, str]:
    global _cached_token
    keyring.set_password(SERVICE, TOKEN_KEY, token)
    _cached_token = token
    try:
        result = _api("getMe", token)
        if result.get("ok"):
            bot = result["result"]
            return True, f"@{bot.get('username', '?')}"
        return False, "getMe failed — check the token"
    except requests.RequestException as e:
        return False, f"token saved but connection failed: {e}"


def whoami() -> dict[str, Any] | None:
    tok = _token()
    if not tok:
        return None
    try:
        result = _api("getMe", tok)
        if result.get("ok"):
            return result["result"]
    except requests.RequestException:
        pass
    return None

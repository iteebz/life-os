import contextlib
import threading
from pathlib import Path
from typing import Any

import keyring
import requests

from life.lib.resolve import resolve_people_field
from life.lib.store import get_db

SERVICE = "life-cli-telegram"
TOKEN_KEY = "bot_token"  # noqa: S105
API = "https://api.telegram.org/bot{token}"

_cached_token: str | None = None
_cached_update_id: int | None = None
_poll_lock = threading.Lock()
_PHOTO_DIR = Path.home() / ".life" / "images"


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
                "INSERT OR IGNORE INTO messages "
                "(id, channel, direction, peer, peer_name, body, timestamp, success) "
                "VALUES (?, 'telegram', 'out', ?, 'steward', ?, ?, 1)",
                (f"tg-{message_id}", str(chat_id), body, ts),
            )
    except Exception:  # noqa: S110
        pass


def poll(timeout: int = 5, token: str | None = None) -> list[dict[str, Any]]:
    tok = token or _token()
    if not tok:
        return []

    with _poll_lock:
        return _poll(tok, timeout)


def _poll(tok: str, timeout: int) -> list[dict[str, Any]]:
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
        if not msg:
            continue
        has_text = bool(msg.get("text"))
        has_photo = bool(msg.get("photo"))
        if not has_text and not has_photo:
            continue
        sender = msg.get("from", {})
        last_name = sender.get("last_name", "")
        body = msg.get("text") or msg.get("caption") or "[photo]"
        photo_path = _download_photo(msg, tok) if has_photo else None
        parsed = {
            "id": msg["message_id"],
            "chat_id": msg["chat"]["id"],
            "from_id": sender.get("id"),
            "from_name": (
                sender.get("first_name", "") + (" " + last_name if last_name else "")
            ).strip(),
            "body": body,
            "photo_path": photo_path,
            "timestamp": msg["date"],
        }
        messages.append(parsed)
        _store_incoming(parsed)

    return messages



def _download_photo(msg: dict[str, Any], token: str) -> str | None:
    """Download the largest photo size via getFile. Returns local path or None."""
    photos = msg.get("photo", [])
    if not photos:
        return None
    best = max(photos, key=lambda p: p.get("file_size", 0))
    file_id = best.get("file_id")
    if not file_id:
        return None
    try:
        result = _api("getFile", token, file_id=file_id)
        if not result.get("ok"):
            return None
        file_path = result["result"].get("file_path")
        if not file_path:
            return None
        url = f"https://api.telegram.org/file/bot{token}/{file_path}"
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        _PHOTO_DIR.mkdir(parents=True, exist_ok=True)
        ext = Path(file_path).suffix or ".jpg"
        local = _PHOTO_DIR / f"tg-{msg['message_id']}{ext}"
        local.write_bytes(resp.content)
        return str(local)
    except Exception:
        return None


def get_history(
    chat_id: int | None = None, limit: int = 50, hours: int | None = None
) -> list[dict[str, Any]]:
    """Read stored telegram messages from DB."""
    conditions = ["channel = 'telegram'"]
    params: list[Any] = []
    if chat_id is not None:
        conditions.append("peer = ?")
        params.append(str(chat_id))
    if hours is not None:
        import time
        cutoff = int(time.time()) - (hours * 3600)
        conditions.append("timestamp > ?")
        params.append(cutoff)
    where = " AND ".join(conditions)
    params.append(limit)
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT id, direction, peer, peer_name, body, timestamp "
            f"FROM messages WHERE {where} ORDER BY timestamp DESC LIMIT ?",
            params,
        ).fetchall()
    return [
        {
            "id": r[0],
            "direction": r[1],
            "peer": r[2],
            "peer_name": r[3],
            "body": r[4],
            "timestamp": r[5],
        }
        for r in rows
    ]


def _store_incoming(msg: dict[str, Any]) -> None:
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO messages "
                "(id, channel, direction, peer, peer_name, body, timestamp) "
                "VALUES (?, 'telegram', 'in', ?, ?, ?, ?)",
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

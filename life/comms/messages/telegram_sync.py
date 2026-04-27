"""Telegram user API sync — full chat history via Telethon.

First run requires interactive phone auth (one-time).
Session persists at ~/.life/telegram/user.session.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import keyring
from telethon import TelegramClient
from telethon.tl.types import MessageMediaPhoto, User

from life.lib.store import get_db

SESSION_DIR = Path.home() / ".life" / "telegram"
SESSION_PATH = SESSION_DIR / "user"
IMAGE_DIR = Path.home() / ".life" / "images"

SERVICE = "life-cli-telegram"
API_ID_KEY = "api_id"
API_HASH_KEY = "api_hash"


def _get_credentials() -> tuple[int, str] | None:
    api_id = keyring.get_password(SERVICE, API_ID_KEY)
    api_hash = keyring.get_password(SERVICE, API_HASH_KEY)
    if api_id and api_hash:
        return int(api_id), api_hash
    return None


def save_credentials(api_id: int, api_hash: str) -> None:
    keyring.set_password(SERVICE, API_ID_KEY, str(api_id))
    keyring.set_password(SERVICE, API_HASH_KEY, api_hash)


def _last_synced_ts(peer: str) -> int:
    """Get the most recent timestamp for a peer in messages table."""
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT MAX(timestamp) FROM messages "
                "WHERE channel = 'telegram' AND peer = ?",
                (peer,),
            ).fetchone()
            return row[0] or 0 if row else 0
    except Exception:
        return 0


def _store_message(
    msg_id: int,
    direction: str,
    peer: str,
    peer_name: str,
    body: str,
    timestamp: int,
    image_path: str | None = None,
) -> None:
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO messages "
                "(id, channel, direction, peer, peer_name, body, timestamp, image_path) "
                "VALUES (?, 'telegram', ?, ?, ?, ?, ?, ?)",
                (f"tg-{msg_id}", direction, peer, peer_name, body, timestamp, image_path),
            )
    except Exception:  # noqa: S110
        pass


async def _download_media(client: Any, message: Any, msg_id: int) -> str | None:
    """Download photo/media from a message. Returns local path."""
    if not message.media:
        return None
    try:
        if not isinstance(message.media, MessageMediaPhoto):
            return None
        IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        path = IMAGE_DIR / f"tg-{msg_id}.jpg"
        if path.exists():
            return str(path)
        await client.download_media(message, file=str(path))
        return str(path) if path.exists() else None
    except Exception:
        return None


async def _sync_chat(
    client: Any,
    chat: str | int,
    limit: int | None = None,
    incremental: bool = True,
) -> int:
    """Sync messages from a single chat. Returns count synced."""
    entity = await client.get_entity(chat)
    me = await client.get_me()

    peer_id = str(entity.id)
    if isinstance(entity, User):
        peer_name = (
            (entity.first_name or "") + (" " + entity.last_name if entity.last_name else "")
        ).strip() or str(entity.id)
    else:
        peer_name = getattr(entity, "title", str(entity.id))

    min_ts = _last_synced_ts(peer_id) if incremental else 0

    count = 0
    async for message in client.iter_messages(entity, limit=limit):
        if not message.date:
            continue
        ts = int(message.date.timestamp())
        if incremental and ts <= min_ts:
            break

        is_outgoing = message.out or (message.sender_id == me.id)
        direction = "out" if is_outgoing else "in"
        body = message.text or message.message or ""

        image_path = await _download_media(client, message, message.id)

        if not body and not image_path:
            continue

        if not body and image_path:
            body = "[photo]"

        sender_name = "steward" if is_outgoing else peer_name
        _store_message(message.id, direction, peer_id, sender_name, body, ts, image_path)
        count += 1

    return count


async def _run_sync(
    chat: str | int,
    limit: int | None = None,
    full: bool = False,
) -> int:
    creds = _get_credentials()
    if not creds:
        raise ValueError(
            "telegram user API not configured — run: life comms telegram auth <api_id> <api_hash>"
        )

    api_id, api_hash = creds
    SESSION_DIR.mkdir(parents=True, exist_ok=True)

    client = TelegramClient(str(SESSION_PATH), api_id, api_hash)
    await client.start()  # type: ignore[misc]

    try:
        return await _sync_chat(client, chat, limit=limit, incremental=not full)
    finally:
        await client.disconnect()  # type: ignore[misc]


def sync(chat: str | int, limit: int | None = None, full: bool = False) -> int:
    """Sync telegram chat history. Returns message count."""
    return asyncio.run(_run_sync(chat, limit=limit, full=full))

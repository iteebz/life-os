"""Unified messaging surface across all channels.

life messages                             recent messages, all channels
life messages <person>                    full conversation with person
life messages <person> --sent             only outbound (steward → person)
life messages <person> --received         only inbound (person → steward)
life messages <person> --channel tg       filter by channel (tg, signal, chat)
life messages <person> -s "keyword"       search within conversation
life messages <person> --since 7d         time filter
life messages <person> -n 50             last N messages
life message <person> "text"               send a message (auto-routes channel)
"""

import re
import time
from datetime import datetime
from typing import Any

from fncli import cli

from life.comms.messages import signal
from life.comms.messages import telegram as _tg
from life.comms.messages.telegram_sync import save_credentials, sync
from life.core.errors import LifeError, ValidationError
from life.lib.store import get_db

_CHANNEL_ALIASES = {"tg": "telegram", "tel": "telegram", "sig": "signal"}


def _parse_since(since: str) -> int:
    """Parse '7d', '24h', '2w' into a unix timestamp cutoff."""
    m = re.match(r"^(\d+)([dhw])$", since.strip().lower())
    if not m:
        raise ValidationError(f"bad --since format: '{since}' (use 7d, 24h, 2w)")
    n, unit = int(m.group(1)), m.group(2)
    seconds = {"h": 3600, "d": 86400, "w": 604800}[unit]
    return int(time.time()) - (n * seconds)


def _resolve_channel(raw: str) -> str:
    """Normalize channel name: tg → telegram, sig → signal."""
    return _CHANNEL_ALIASES.get(raw.lower(), raw.lower())


def _resolve_peer(name: str) -> tuple[str | None, str | None]:
    """Resolve a name to (peer_id, channel). Returns (None, None) if unresolvable.

    Checks people profiles first (signal number, telegram chat_id),
    then falls back to peer_name match in messages table.
    """
    # people profile: telegram
    tg_id = _tg.resolve_chat_id(name)
    if tg_id is not None:
        return str(tg_id), "telegram"

    # people profile: signal
    sig = signal.resolve_contact(name)
    if sig != name:  # resolve_contact returns input unchanged on miss
        return sig, "signal"

    # fallback: match peer_name in messages table (any channel)
    with get_db() as conn:
        row = conn.execute(
            "SELECT DISTINCT peer, channel FROM messages WHERE peer_name = ? COLLATE NOCASE ORDER BY timestamp DESC LIMIT 1",
            (name,),
        ).fetchone()
    if row:
        return row[0], row[1]

    return None, None


def _query(
    peer_id: str | None = None,
    channel: str | None = None,
    direction: str | None = None,
    limit: int = 0,
    since: str = "",
    search: str = "",
) -> list[dict[str, Any]]:
    conditions: list[str] = []
    params: list[Any] = []

    if peer_id:
        conditions.append("peer = ?")
        params.append(peer_id)
    if channel:
        conditions.append("channel = ?")
        params.append(channel)
    if direction:
        conditions.append("direction = ?")
        params.append(direction)
    if since:
        conditions.append("timestamp > ?")
        params.append(_parse_since(since))
    if search:
        conditions.append("body LIKE ?")
        params.append(f"%{search}%")

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    if limit > 0:
        sql = (
            f"SELECT * FROM ("  # noqa: S608
            f"SELECT id, channel, direction, peer, peer_name, body, timestamp, image_path "
            f"FROM messages {where} ORDER BY timestamp DESC LIMIT ?"
            f") sub ORDER BY timestamp ASC"
        )
        params.append(limit)
    else:
        sql = (
            f"SELECT id, channel, direction, peer, peer_name, body, timestamp, image_path "  # noqa: S608
            f"FROM messages {where} ORDER BY timestamp ASC"
        )

    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()

    return [
        {
            "id": r[0],
            "channel": r[1],
            "direction": r[2],
            "peer": r[3],
            "peer_name": r[4],
            "body": r[5],
            "timestamp": r[6],
            "image_path": r[7],
        }
        for r in rows
    ]


def _format(msgs: list[dict[str, Any]], context: str = "") -> None:
    if not msgs:
        print(f"no messages{' with ' + context if context else ''}")
        return

    last_date = ""
    last_channel = ""
    for m in msgs:
        dt = datetime.fromtimestamp(m["timestamp"]) if m["timestamp"] else None
        if dt:
            date_str = dt.strftime("%Y-%m-%d")
            if date_str != last_date:
                print(f"\n  ── {date_str} ──")
                last_date = date_str
            ts = dt.strftime("%H:%M")
        else:
            ts = "??:??"

        # channel tag when showing mixed channels or channel switches
        ch = ""
        if not context or (m["channel"] != last_channel and last_channel):
            ch = f"[{m['channel']}] "
        last_channel = m["channel"]

        if m["direction"] == "out":
            label = "you"
        else:
            label = m["peer_name"] or m["peer"]

        body = m["body"] or ""
        if m.get("image_path"):
            body = f"[image: {m['image_path']}]" if not body or body == "[photo]" else f"{body} [image]"

        print(f"  {ts}  {ch}{label}: {body}")

    print(f"\n  {len(msgs)} messages")


@cli(
    "life messages",
    name="list",
    default=True,
    flags={
        "person": [],
        "limit": ["-n"],
        "search": ["-s"],
        "since": ["--since"],
        "channel": ["-c", "--channel"],
        "sent": ["--sent"],
        "received": ["--received"],
    },
)
def messages(
    person: str = "",
    limit: int = 0,
    since: str = "",
    search: str = "",
    channel: str = "",
    sent: bool = False,
    received: bool = False,
):
    """View message history"""
    if sent and received:
        raise ValidationError("pick one: --sent or --received")

    direction = None
    if sent:
        direction = "out"
    elif received:
        direction = "in"

    resolved_channel = _resolve_channel(channel) if channel else None

    peer_id = None
    peer_channel = None
    context = person

    if person:
        peer_id, peer_channel = _resolve_peer(person)
        if peer_id is None:
            raise ValidationError(f"can't resolve '{person}' — add to people profile or use raw ID")

    # explicit --channel overrides peer's default channel for filtering
    filter_channel = resolved_channel or (peer_channel if person else None)

    if not person and not since and limit == 0:
        limit = 50

    msgs = _query(peer_id=peer_id, channel=filter_channel, direction=direction, limit=limit, since=since, search=search)
    _format(msgs, context)


@cli("life messages", name="sync", flags={"full": ["--full"]})
def sync_cmd(person: str, full: bool = False):
    """Sync message history from telegram"""
    chat_id = _tg.resolve_chat_id(person)
    chat_ref: str | int = chat_id if chat_id is not None else person

    n = sync(chat_ref, full=full)
    print(f"synced {n} messages from {person}")


@cli("life messages", name="auth")
def auth_cmd(api_id: int, api_hash: str):
    """Store Telegram user API credentials (from my.telegram.org)"""
    save_credentials(api_id, api_hash)
    print(f"saved — api_id={api_id}. run: life messages sync <person> to pull history")


@cli("life message", name="send", default=True, flags={"channel": ["-c", "--channel"]})
def send_cmd(person: str, text: str, channel: str = ""):
    """Send a message (auto-routes telegram or signal)"""
    peer_id, peer_channel = _resolve_peer(person)
    if peer_id is None:
        raise ValidationError(f"can't resolve '{person}' — add to people profile or use raw ID")

    use_channel = _resolve_channel(channel) if channel else peer_channel

    if use_channel == "telegram":
        success, result = _tg.send(int(peer_id), text)
    elif use_channel == "signal":
        success, result = signal.send(peer_id, text)
    else:
        raise ValidationError(f"unknown channel '{use_channel}' for {person}")

    if success:
        print(f"sent → {person} ({use_channel})")
    else:
        raise LifeError(f"failed: {result}")

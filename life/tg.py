"""Clean telegram conversation viewer.

life tg <person>                  full conversation
life tg <person> --since 7d       last N days/hours
life tg <person> -s "keyword"     search within conversation
life tg <person> -n 50            last N messages
life tg sync <person>             incremental sync from telegram
life tg sync <person> --full      full re-sync
life tg auth <api_id> <hash>      one-time user API setup
"""

import re
import time
from datetime import datetime
from typing import Any

from fncli import cli

from life.comms.messages import telegram as _tg
from life.core.errors import ValidationError
from life.lib.store import get_db


def _parse_since(since: str) -> int:
    """Parse '7d', '24h', '2w' into a unix timestamp cutoff."""
    m = re.match(r"^(\d+)([dhw])$", since.strip().lower())
    if not m:
        raise ValidationError(f"bad --since format: '{since}' (use 7d, 24h, 2w)")
    n, unit = int(m.group(1)), m.group(2)
    seconds = {"h": 3600, "d": 86400, "w": 604800}[unit]
    return int(time.time()) - (n * seconds)


def _resolve_peer(name: str) -> str:
    """Resolve a name to a telegram peer (chat_id string). Tries people profiles, then DB peer_name."""
    chat_id = _tg.resolve_chat_id(name)
    if chat_id is not None:
        return str(chat_id)
    # fallback: match peer_name in messages table
    with get_db() as conn:
        row = conn.execute(
            "SELECT DISTINCT peer FROM messages WHERE channel = 'telegram' AND peer_name = ? COLLATE NOCASE",
            (name,),
        ).fetchone()
    if row:
        return row[0]
    raise ValidationError(f"can't resolve '{name}' — check people profile or use chat_id")


def _query_messages(
    peer: str,
    limit: int = 0,
    since: str = "",
    search: str = "",
) -> list[dict[str, Any]]:
    """Query messages table for a telegram conversation."""
    peer_id = _resolve_peer(peer)

    conditions = ["channel = 'telegram'", "peer = ?"]
    params: list[Any] = [peer_id]

    if since:
        cutoff = _parse_since(since)
        conditions.append("timestamp > ?")
        params.append(cutoff)

    if search:
        conditions.append("body LIKE ?")
        params.append(f"%{search}%")

    where = " AND ".join(conditions)
    order = "ORDER BY timestamp ASC"

    if limit > 0:
        # get last N, but display ascending
        sql = (
            f"SELECT * FROM ("  # noqa: S608
            f"SELECT id, direction, peer_name, body, timestamp, photo_path "
            f"FROM messages WHERE {where} ORDER BY timestamp DESC LIMIT ?"
            f") sub ORDER BY timestamp ASC"
        )
        params.append(limit)
    else:
        sql = (
            f"SELECT id, direction, peer_name, body, timestamp, photo_path "  # noqa: S608
            f"FROM messages WHERE {where} {order}"
        )

    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()

    return [
        {
            "id": r[0],
            "direction": r[1],
            "peer_name": r[2],
            "body": r[3],
            "timestamp": r[4],
            "photo_path": r[5],
        }
        for r in rows
    ]


def _format_messages(msgs: list[dict[str, Any]], peer: str) -> None:
    """Print messages as a clean conversation."""
    if not msgs:
        print(f"no messages with {peer}")
        return

    last_date = ""
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

        if m["direction"] == "out":
            label = "you"
        else:
            label = m["peer_name"] or peer

        body = m["body"] or ""
        if m.get("photo_path"):
            body = f"[photo: {m['photo_path']}]" if not body or body == "[photo]" else f"{body} [photo]"

        print(f"  {ts}  {label}: {body}")

    print(f"\n  {len(msgs)} messages")


@cli("life tg", default=True, flags={"limit": ["-n"], "search": ["-s"], "since": ["--since"]})
def tg_cmd(person: str, limit: int = 0, since: str = "", search: str = ""):
    """View telegram conversation history"""
    msgs = _query_messages(person, limit=limit, since=since, search=search)
    _format_messages(msgs, person)


@cli("life tg sync", flags={"full": ["--full"]})
def tg_sync_cmd(person: str, full: bool = False):
    """Sync telegram chat history from the cloud"""
    from life.comms.messages.telegram_sync import sync

    chat_id = _tg.resolve_chat_id(person)
    if chat_id is None:
        # try raw — might be a username
        chat_ref: str | int = person
    else:
        chat_ref = chat_id

    n = sync(chat_ref, full=full)
    print(f"synced {n} messages from {person}")


@cli("life tg", name="auth")
def tg_auth_cmd(api_id: int, api_hash: str):
    """Store Telegram user API credentials (from my.telegram.org)"""
    from life.comms.messages.telegram_sync import save_credentials

    save_credentials(api_id, api_hash)
    print(f"saved — api_id={api_id}. run: life tg sync <person> to pull history")

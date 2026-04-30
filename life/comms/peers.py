"""Peer resolution. Channel-native address → stable peer identity."""

from life.lib.store import get_db


def resolve_or_create(channel: str, address: str, display_name: str | None = None) -> int:
    """Return peer_id for (channel, address). Creates peer + address if new.

    display_name updates the peer's name if provided and the existing name is
    just the raw address (i.e. unresolved).
    """
    address = str(address)
    with get_db() as conn:
        row = conn.execute(
            "SELECT peer_id FROM peer_addresses WHERE channel = ? AND address = ?",
            (channel, address),
        ).fetchone()
        if row:
            peer_id = row[0]
            if display_name:
                conn.execute(
                    "UPDATE peers SET display_name = ? WHERE id = ? AND display_name = ?",
                    (display_name, peer_id, address),
                )
            return peer_id

        cursor = conn.execute(
            "INSERT INTO peers (display_name) VALUES (?)",
            (display_name or address,),
        )
        peer_id = cursor.lastrowid
        conn.execute(
            "INSERT INTO peer_addresses (peer_id, channel, address) VALUES (?, ?, ?)",
            (peer_id, channel, address),
        )
        return peer_id

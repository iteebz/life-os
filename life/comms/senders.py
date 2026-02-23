"""Sender statistics — track response patterns to inform triage priority."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime

from . import db


@dataclass
class SenderStat:
    sender: str
    received_count: int
    replied_count: int
    archived_count: int
    deleted_count: int
    flagged_count: int
    avg_response_hours: float | None
    response_rate: float
    priority_score: float


def _normalize_sender(sender: str) -> str:
    match = re.search(r"<([^>]+)>", sender)
    if match:
        return match.group(1).lower().strip()
    return sender.lower().strip()


def _sender_id(sender: str) -> str:
    normalized = _normalize_sender(sender)
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def record_received(sender: str) -> None:
    normalized_sender = _normalize_sender(sender)
    sender_hash = _sender_id(sender)
    now = datetime.now().isoformat()

    with db.get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM sender_stats WHERE id = ?", (sender_hash,)
        ).fetchone()

        if existing:
            conn.execute(
                """UPDATE sender_stats
                SET received_count = received_count + 1,
                    last_received_at = ?,
                    updated_at = ?
                WHERE id = ?""",
                (now, now, sender_hash),
            )
        else:
            conn.execute(
                """INSERT INTO sender_stats (id, sender, received_count, last_received_at, updated_at)
                VALUES (?, ?, 1, ?, ?)""",
                (sender_hash, normalized_sender, now, now),
            )


def record_action(sender: str, action: str, response_hours: float | None = None) -> None:
    normalized_sender = _normalize_sender(sender)
    sender_hash = _sender_id(sender)
    now = datetime.now().isoformat()

    column_map = {
        "reply": "replied_count",
        "archive": "archived_count",
        "delete": "deleted_count",
        "flag": "flagged_count",
    }

    column = column_map.get(action)
    if not column:
        return

    with db.get_db() as conn:
        existing = conn.execute(
            "SELECT id, avg_response_hours, replied_count FROM sender_stats WHERE id = ?",
            (sender_hash,),
        ).fetchone()

        if existing:
            if action == "reply" and response_hours is not None:
                old_avg: float = existing["avg_response_hours"] or 0.0
                old_count: int = existing["replied_count"] or 0
                new_avg = ((old_avg * old_count) + response_hours) / (old_count + 1)
                conn.execute(
                    f"UPDATE sender_stats SET {column} = {column} + 1, avg_response_hours = ?, last_action_at = ?, updated_at = ? WHERE id = ?",  # noqa: S608
                    (new_avg, now, now, sender_hash),
                )
            else:
                conn.execute(
                    f"UPDATE sender_stats SET {column} = {column} + 1, last_action_at = ?, updated_at = ? WHERE id = ?",  # noqa: S608
                    (now, now, sender_hash),
                )
        else:
            conn.execute(
                f"INSERT INTO sender_stats (id, sender, {column}, last_action_at, updated_at) VALUES (?, ?, 1, ?, ?)",  # noqa: S608
                (sender_hash, normalized_sender, now, now),
            )


def get_sender_stat(sender: str) -> SenderStat | None:
    sender_hash = _sender_id(sender)

    with db.get_db() as conn:
        row = conn.execute("SELECT * FROM sender_stats WHERE id = ?", (sender_hash,)).fetchone()

    if not row:
        return None

    total_actions = (
        row["replied_count"] + row["archived_count"] + row["deleted_count"] + row["flagged_count"]
    )

    response_rate = row["replied_count"] / total_actions if total_actions > 0 else 0

    priority_score = _calculate_priority(
        received=row["received_count"],
        replied=row["replied_count"],
        archived=row["archived_count"],
        deleted=row["deleted_count"],
        flagged=row["flagged_count"],
        avg_response_hours=row["avg_response_hours"],
    )

    return SenderStat(
        sender=row["sender"],
        received_count=row["received_count"],
        replied_count=row["replied_count"],
        archived_count=row["archived_count"],
        deleted_count=row["deleted_count"],
        flagged_count=row["flagged_count"],
        avg_response_hours=row["avg_response_hours"],
        response_rate=response_rate,
        priority_score=priority_score,
    )


def _calculate_priority(
    received: int,
    replied: int,
    archived: int,
    deleted: int,
    flagged: int,
    avg_response_hours: float | None,
) -> float:
    total = replied + archived + deleted + flagged
    if total < 3:
        return 0.5

    reply_weight = replied / total if total > 0 else 0
    delete_weight = deleted / total if total > 0 else 0
    flag_weight = flagged / total if total > 0 else 0

    score = 0.5
    score += reply_weight * 0.3
    score += flag_weight * 0.2
    score -= delete_weight * 0.2

    if avg_response_hours is not None:
        if avg_response_hours < 4:
            score += 0.1
        elif avg_response_hours > 48:
            score -= 0.1

    return max(0.0, min(1.0, score))


def get_top_senders(limit: int = 20) -> list[SenderStat]:
    with db.get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM sender_stats
            WHERE received_count > 0
            ORDER BY received_count DESC
            LIMIT ?""",
            (limit,),
        ).fetchall()

    stats = []
    for row in rows:
        total_actions = (
            row["replied_count"]
            + row["archived_count"]
            + row["deleted_count"]
            + row["flagged_count"]
        )
        response_rate = row["replied_count"] / total_actions if total_actions > 0 else 0

        priority_score = _calculate_priority(
            received=row["received_count"],
            replied=row["replied_count"],
            archived=row["archived_count"],
            deleted=row["deleted_count"],
            flagged=row["flagged_count"],
            avg_response_hours=row["avg_response_hours"],
        )

        stats.append(
            SenderStat(
                sender=row["sender"],
                received_count=row["received_count"],
                replied_count=row["replied_count"],
                archived_count=row["archived_count"],
                deleted_count=row["deleted_count"],
                flagged_count=row["flagged_count"],
                avg_response_hours=row["avg_response_hours"],
                response_rate=response_rate,
                priority_score=priority_score,
            )
        )

    return stats


def format_sender_context_for_prompt(sender: str) -> str:
    stat = get_sender_stat(sender)
    if not stat or stat.received_count < 3:
        return ""

    parts = [f"SENDER HISTORY ({stat.sender}):"]
    parts.append(f"- Received: {stat.received_count}, Replied: {stat.replied_count}")
    parts.append(f"- Response rate: {stat.response_rate:.0%}")
    parts.append(f"- Priority score: {stat.priority_score:.2f}")

    if stat.avg_response_hours is not None:
        parts.append(f"- Avg response time: {stat.avg_response_hours:.1f}h")

    if stat.deleted_count > stat.replied_count:
        parts.append("- Pattern: Usually deleted/ignored")
    elif stat.archived_count > stat.replied_count:
        parts.append("- Pattern: Usually archived without reply")
    elif stat.replied_count > 0:
        parts.append("- Pattern: Usually responded to")

    return "\n".join(parts)

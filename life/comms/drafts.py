import uuid
from datetime import datetime

from .db import get_db, now_iso
from .models import Draft


def create_draft(
    to_addr: str,
    subject: str,
    body: str,
    from_account_id: str | None = None,
    from_addr: str | None = None,
    thread_id: str | None = None,
    cc_addr: str | None = None,
    claude_reasoning: str | None = None,
) -> str:
    draft_id = str(uuid.uuid4())

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO drafts (id, thread_id, to_addr, cc_addr, subject, body, claude_reasoning, from_account_id, from_addr)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                draft_id,
                thread_id,
                to_addr,
                cc_addr,
                subject,
                body,
                claude_reasoning,
                from_account_id,
                from_addr,
            ),
        )

    return draft_id


def resolve_draft_id(draft_id_prefix: str) -> str | None:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id FROM drafts WHERE id LIKE ? ORDER BY created_at DESC",
            (f"{draft_id_prefix}%",),
        ).fetchall()

    if len(rows) == 0:
        return None
    if len(rows) == 1:
        return rows[0]["id"]
    return None


def get_draft(draft_id: str) -> Draft | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()

        if not row:
            return None

        row_dict = dict(row)
        return Draft(
            id=row_dict["id"],
            thread_id=row_dict["thread_id"],
            message_id=None,
            to_addr=row_dict["to_addr"],
            cc_addr=row_dict["cc_addr"],
            subject=row_dict["subject"],
            body=row_dict["body"],
            claude_reasoning=row_dict["claude_reasoning"],
            from_account_id=row_dict.get("from_account_id"),
            from_addr=row_dict.get("from_addr"),
            created_at=datetime.fromisoformat(row_dict["created_at"]),
            approved_at=datetime.fromisoformat(row_dict["approved_at"])
            if row_dict["approved_at"]
            else None,
            sent_at=datetime.fromisoformat(row_dict["sent_at"]) if row_dict["sent_at"] else None,
        )


def approve_draft(draft_id: str) -> None:
    with get_db() as conn:
        conn.execute("UPDATE drafts SET approved_at = ? WHERE id = ?", (now_iso(), draft_id))


def mark_sent(draft_id: str) -> None:
    with get_db() as conn:
        conn.execute("UPDATE drafts SET sent_at = ? WHERE id = ?", (now_iso(), draft_id))


def list_pending_drafts() -> list[Draft]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM drafts
            WHERE approved_at IS NULL AND sent_at IS NULL
            ORDER BY created_at DESC
            """
        ).fetchall()

        return [
            Draft(
                id=row["id"],
                thread_id=row["thread_id"],
                message_id=None,
                to_addr=row["to_addr"],
                cc_addr=row["cc_addr"],
                subject=row["subject"],
                body=row["body"],
                claude_reasoning=row["claude_reasoning"],
                from_account_id=dict(row).get("from_account_id"),
                from_addr=dict(row).get("from_addr"),
                created_at=datetime.fromisoformat(row["created_at"]),
                approved_at=None,
                sent_at=None,
            )
            for row in rows
        ]

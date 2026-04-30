import uuid
from typing import Any

from life.lib.store import get_db

from .config import add_account as config_add_account


def add_email_account(provider: str, email: str) -> str:
    account_id = str(uuid.uuid4())

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO accounts (id, service_type, provider, email, enabled)
            VALUES (?, ?, ?, ?, ?)
            """,
            (account_id, "email", provider, email, 1),
        )

    config_add_account("email", {"provider": provider, "email": email, "id": account_id})

    return account_id


def add_messaging_account(provider: str, identifier: str) -> str:
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM accounts WHERE provider = ? AND email = ?",
            (provider, identifier),
        ).fetchone()
        if existing:
            return existing["id"]

    account_id = str(uuid.uuid4())

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO accounts (id, service_type, provider, email, enabled)
            VALUES (?, ?, ?, ?, ?)
            """,
            (account_id, "messaging", provider, identifier, 1),
        )

    config_add_account("messaging", {"provider": provider, "identifier": identifier, "id": account_id})

    return account_id


def get_account_by_id(account_id: str):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if row:
            return dict(row)
    return None


def list_accounts(service_type: str | None = None):
    with get_db() as conn:
        if service_type:
            rows = conn.execute("SELECT * FROM accounts WHERE service_type = ?", (service_type,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM accounts").fetchall()
        return [dict(row) for row in rows]


def select_email_account(email: str | None) -> tuple[dict[str, Any] | None, str | None]:
    accounts = list_accounts("email")
    if not accounts:
        return None, "No email accounts linked. Run: comms link gmail"

    if email is None:
        if len(accounts) == 1:
            return accounts[0], None
        return None, "Multiple accounts found. Specify --email"

    for account in accounts:
        if account["email"] == email:
            return account, None

    return None, f"Account not found: {email}"


def remove_account(account_id: str) -> bool:
    with get_db() as conn:
        cursor = conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        return cursor.rowcount > 0

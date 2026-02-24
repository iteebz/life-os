from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import accounts as accts_module
from . import drafts, senders
from .adapters.email import gmail, outlook


def _resolve_email_account(email: str | None) -> dict[str, Any]:
    account, error = accts_module.select_email_account(email)
    if account:
        return account
    raise ValueError(error or "No email account found")


def _get_email_adapter(provider: str):
    if provider == "gmail":
        return gmail
    if provider == "outlook":
        return outlook
    raise ValueError(f"Provider {provider} not supported")


def compose_email_draft(
    to_addr: str,
    subject: str | None,
    body: str,
    cc_addr: str | None,
    email: str | None,
) -> tuple[str, str]:
    account = _resolve_email_account(email)
    from_addr = account["email"]

    draft_id = drafts.create_draft(
        to_addr=to_addr,
        subject=subject or "(no subject)",
        body=body,
        cc_addr=cc_addr,
        from_account_id=account["id"],
        from_addr=from_addr,
    )

    return draft_id, from_addr


def _extract_email(addr: str) -> str:
    if "<" in addr and ">" in addr:
        return addr.split("<")[1].split(">")[0].strip()
    return addr.strip()


def _build_reply_recipients(
    messages: list[dict[str, Any]], my_email: str, reply_all: bool
) -> tuple[str, str | None]:
    last_message = messages[-1]
    original_from = last_message["from"]
    to_addr = original_from

    if not reply_all:
        return to_addr, None

    all_recipients: set[str] = set()
    my_email_lower = my_email.lower()

    for message in messages:
        for field in ["from", "to", "cc"]:
            raw = message.get(field, "")
            if not raw:
                continue
            for part in raw.split(","):
                email_addr = _extract_email(part)
                if email_addr and email_addr.lower() != my_email_lower:
                    all_recipients.add(email_addr)

    to_email = _extract_email(original_from)
    all_recipients.discard(to_email)

    cc_addr = ", ".join(sorted(all_recipients)) if all_recipients else None
    return to_addr, cc_addr


def reply_to_thread(
    thread_id: str,
    body: str,
    email: str | None,
    reply_all: bool = False,
) -> tuple[str, str, str, str | None]:
    account = _resolve_email_account(email)
    adapter = _get_email_adapter(account["provider"])
    from_addr = account["email"]

    messages = adapter.fetch_thread_messages(thread_id, from_addr)
    if not messages:
        raise ValueError(f"Thread not found: {thread_id}")

    original_subject = messages[0]["subject"]
    reply_subject = (
        original_subject if original_subject.startswith("Re: ") else f"Re: {original_subject}"
    )

    to_addr, cc_addr = _build_reply_recipients(messages, from_addr, reply_all)

    draft_id = drafts.create_draft(
        to_addr=to_addr,
        subject=reply_subject,
        body=body,
        cc_addr=cc_addr,
        thread_id=thread_id,
        from_account_id=account["id"],
        from_addr=from_addr,
    )

    return draft_id, to_addr, reply_subject, cc_addr


def send_draft(draft_id: str) -> None:
    d = drafts.get_draft(draft_id)
    if not d:
        raise ValueError(f"Draft {draft_id} not found")
    if d.sent_at:
        raise ValueError("Draft already sent")
    if not d.approved_at:
        raise ValueError("Draft requires approval before sending")
    if not d.from_account_id or not d.from_addr:
        raise ValueError("Draft missing source account info")

    account = accts_module.get_account_by_id(d.from_account_id)
    if not account:
        raise ValueError(f"Account not found: {d.from_account_id}")

    adapter = _get_email_adapter(account["provider"])
    success = adapter.send_message(account["id"], d.from_addr, d)

    if not success:
        raise ValueError("Failed to send")

    drafts.mark_sent(draft_id)

    if d.to_addr:
        senders.record_action(d.to_addr, "reply")


def list_threads(label: str) -> list[dict[str, Any]]:
    accounts = accts_module.list_accounts("email")
    results = []
    for account in accounts:
        try:
            adapter = _get_email_adapter(account["provider"])
            threads = adapter.list_threads(account["email"], label=label)
            results.append({"account": account, "threads": threads})
        except ValueError:
            continue
    return results


@dataclass
class InboxItem:
    source: str
    source_id: str
    sender: str
    subject: str
    preview: str
    timestamp: int
    unread: bool
    item_id: str


def get_unified_inbox(limit: int = 20) -> list[InboxItem]:
    from life.signal import get_messages as signal_get_messages

    items: list[InboxItem] = []

    email_accounts = accts_module.list_accounts("email")
    for account in email_accounts:
        try:
            adapter = _get_email_adapter(account["provider"])
            threads = adapter.list_threads(account["email"], label="inbox", max_results=limit)
            items.extend(
                [
                    InboxItem(
                        source="email",
                        source_id=account["email"],
                        sender=t.get("from", "Unknown"),
                        subject=t.get("subject", ""),
                        preview=t.get("snippet", "")[:60],
                        timestamp=t.get("timestamp", 0),
                        unread="UNREAD" in t.get("labels", []),
                        item_id=t["id"],
                    )
                    for t in threads
                ]
            )
        except ValueError:
            continue

    signal_accounts = accts_module.list_accounts("messaging")
    for account in signal_accounts:
        if account["provider"] == "signal":
            msgs = signal_get_messages(phone=account["email"], limit=limit, unread_only=False)
            items.extend(
                [
                    InboxItem(
                        source="signal",
                        source_id=account["email"],
                        sender=m.get("peer_name") or m.get("peer", "Unknown"),
                        subject="",
                        preview=m.get("body", "")[:60],
                        timestamp=m.get("timestamp", 0),
                        unread=m.get("read_at") is None,
                        item_id=m.get("id", ""),
                    )
                    for m in msgs
                ]
            )

    items.sort(key=lambda x: x.timestamp, reverse=True)
    return items[:limit]


def fetch_thread(thread_id: str, email: str | None) -> list[dict[str, Any]]:
    account = _resolve_email_account(email)
    adapter = _get_email_adapter(account["provider"])
    messages = adapter.fetch_thread_messages(thread_id, account["email"])
    if not messages:
        raise ValueError(f"Thread not found: {thread_id}")
    return messages


def resolve_thread_id(prefix: str, email: str | None) -> str | None:
    account = _resolve_email_account(email)
    adapter = _get_email_adapter(account["provider"])
    if len(prefix) >= 16:
        return prefix

    threads = adapter.list_threads(account["email"], label="inbox", max_results=100)
    threads += adapter.list_threads(account["email"], label="unread", max_results=100)
    for thread in threads:
        if thread["id"].startswith(prefix):
            return thread["id"]
    return None


def thread_action(action: str, thread_id: str, email: str | None) -> None:
    account = _resolve_email_account(email)
    adapter = _get_email_adapter(account["provider"])
    action_fn = _get_thread_action(adapter, action)
    if not action_fn:
        raise ValueError(f"Unknown action: {action}")

    sender = None
    if action in ("archive", "delete", "flag"):
        try:
            messages = adapter.fetch_thread_messages(thread_id, account["email"])
            if messages:
                sender = messages[-1].get("from", "")
        except Exception:
            sender = None

    success = action_fn(thread_id, account["email"])
    if not success:
        raise ValueError(f"Failed to {action} thread")

    if sender and action in ("archive", "delete", "flag"):
        senders.record_action(sender, action)


def _get_thread_action(adapter, action: str):
    action_map = {
        "archive": adapter.archive_thread,
        "delete": adapter.delete_thread,
        "flag": adapter.flag_thread,
        "unflag": adapter.unflag_thread,
        "unarchive": adapter.unarchive_thread,
        "undelete": adapter.undelete_thread,
    }
    return action_map.get(action)

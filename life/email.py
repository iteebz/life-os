"""life comms email — email commands."""

from __future__ import annotations

from fncli import cli

from .lib.errors import exit_error


def _run_service(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ValueError as exc:
        exit_error(str(exc))


@cli("life comms email", name="inbox")
def inbox(limit: int = 20):
    """Unified inbox"""
    from datetime import datetime

    from .comms.services import get_unified_inbox

    items = get_unified_inbox(limit=limit)
    if not items:
        print("inbox empty")
        return
    for item in items:
        ts = datetime.fromtimestamp(item.timestamp / 1000).strftime("%m-%d %H:%M")
        unread = "●" if item.unread else " "
        print(f"{unread} [{ts}] {item.sender[:25]:25} {item.preview}")


@cli("life comms email", name="threads")
def threads(label: str = "inbox"):
    """List threads"""
    from .comms import services

    for entry in services.list_threads(label):
        acct = entry["account"]
        thread_list = entry["threads"]
        print(f"\n{acct['email']} ({label}):")
        if not thread_list:
            print("  no threads")
            continue
        for t in thread_list:
            date_str = t.get("date", "")[:16]
            print(f"  {t['id'][:8]} | {date_str:16} | {t['snippet'][:50]}")


@cli("life comms email", name="thread")
def thread(thread_id: str, email: str | None = None):
    """Fetch and display full thread"""
    from .comms import services

    full_id = _run_service(services.resolve_thread_id, thread_id, email) or thread_id
    messages = _run_service(services.fetch_thread, full_id, email)
    print(f"\nThread: {messages[0]['subject']}")
    print("=" * 80)
    for msg in messages:
        print(f"\nFrom: {msg['from']}")
        print(f"Date: {msg['date']}")
        print(f"\n{msg['body']}\n")
        print("-" * 80)


@cli("life comms email", name="summarize")
def summarize(thread_id: str, email: str | None = None):
    """Summarize thread using Claude"""
    from .comms import claude, services

    full_id = _run_service(services.resolve_thread_id, thread_id, email) or thread_id
    messages = _run_service(services.fetch_thread, full_id, email)
    print(f"summarizing {len(messages)} messages...")
    print(f"\n{claude.summarize_thread(messages)}")


@cli("life comms email", name="compose")
def compose(
    to: str,
    subject: str | None = None,
    body: str | None = None,
    cc: str | None = None,
    email: str | None = None,
):
    """Compose new email draft"""
    if not body:
        exit_error("--body required")
    from .comms.services import compose_email_draft

    draft_id, from_addr = _run_service(
        compose_email_draft, to_addr=to, subject=subject, body=body, cc_addr=cc, email=email
    )
    print(f"draft {draft_id[:8]} — from {from_addr} to {to}")
    print(f"run `life comms email approve {draft_id[:8]}` to approve")


@cli("life comms email", name="reply")
def reply(thread_id: str, body: str | None = None, email: str | None = None, all: bool = False):
    """Reply to thread"""
    if not body:
        exit_error("--body required")
    from .comms.services import reply_to_thread

    draft_id, to_addr, _subject, _cc = _run_service(
        reply_to_thread, thread_id=thread_id, body=body, email=email, reply_all=all
    )
    print(f"reply draft {draft_id[:8]} → {to_addr}")
    print(f"run `life comms email approve {draft_id[:8]}` to approve")


@cli("life comms email", name="draft-reply")
def draft_reply(
    thread_id: str, instructions: str | None = None, email: str | None = None, all: bool = False
):
    """Generate AI reply draft"""
    from .comms import claude, services

    full_id = _run_service(services.resolve_thread_id, thread_id, email) or thread_id
    messages = _run_service(services.fetch_thread, full_id, email)

    context = "\n---\n".join(
        f"From: {m['from']}\nDate: {m['date']}\nBody: {m['body'][:500]}" for m in messages[-5:]
    )
    print("generating draft...")
    body, reasoning = claude.generate_reply(context, instructions)
    if not body:
        exit_error(f"failed: {reasoning}")

    draft_id, to_addr, subject, _cc = _run_service(
        services.reply_to_thread, thread_id=full_id, body=body, email=email, reply_all=all
    )
    print(f"\nreasoning: {reasoning}")
    print(f"\ndraft {draft_id[:8]} → {to_addr}  |  {subject}")
    print(f"\n{body}\n")
    print(f"run `life comms email approve {draft_id[:8]}` to approve")


@cli("life comms email", name="drafts")
def drafts_list():
    """List pending drafts"""
    from .comms.drafts import list_pending_drafts

    pending = list_pending_drafts()
    if not pending:
        print("no pending drafts")
        return
    for d in pending:
        status = "✓ approved" if d.approved_at else "⧗ pending"
        print(f"  {d.id[:8]} | {d.to_addr} | {d.subject or '(no subject)'} | {status}")


@cli("life comms email", name="draft")
def draft_show(draft_id: str):
    """Show draft details"""
    from .comms.drafts import get_draft

    d = get_draft(draft_id)
    if not d:
        exit_error(f"draft {draft_id} not found")
    print(f"To: {d.to_addr}")
    if d.cc_addr:
        print(f"Cc: {d.cc_addr}")
    print(f"Subject: {d.subject or '(no subject)'}")
    print(f"\n{d.body}\n")
    if d.claude_reasoning:
        print(f"--- reasoning ---\n{d.claude_reasoning}")


@cli("life comms email", name="approve")
def approve_draft(draft_id: str):
    """Approve draft for sending"""
    from .comms import drafts as drafts_module

    full_id = drafts_module.resolve_draft_id(draft_id) or draft_id
    d = drafts_module.get_draft(full_id)
    if not d:
        exit_error(f"draft {draft_id} not found")
    if d.approved_at:
        print("already approved")
        return
    drafts_module.approve_draft(full_id)
    print(f"approved {full_id[:8]} — run `life comms email send {full_id[:8]}` to send")


@cli("life comms email", name="send")
def send_draft(draft_id: str):
    """Send approved draft"""
    from .comms import drafts as drafts_module
    from .comms import services

    full_id = drafts_module.resolve_draft_id(draft_id) or draft_id
    d = drafts_module.get_draft(full_id)
    if not d:
        exit_error(f"draft {draft_id} not found")
    _run_service(services.send_draft, full_id)
    print(f"sent → {d.to_addr}  |  {d.subject}")


@cli("life comms email", name="archive")
def archive(thread_id: str, email: str | None = None):
    """Archive thread"""
    from .comms import services

    _run_service(services.thread_action, "archive", thread_id, email)
    print(f"archived {thread_id}")


@cli("life comms email", name="delete")
def delete(thread_id: str, email: str | None = None):
    """Delete thread"""
    from .comms import services

    _run_service(services.thread_action, "delete", thread_id, email)
    print(f"deleted {thread_id}")


@cli("life comms email", name="flag")
def flag(thread_id: str, email: str | None = None):
    """Flag thread"""
    from .comms import services

    _run_service(services.thread_action, "flag", thread_id, email)
    print(f"flagged {thread_id}")


@cli("life comms email", name="snooze")
def snooze(thread_id: str, until: str = "tomorrow", email: str | None = None):
    """Snooze thread"""
    from .comms import services
    from .comms import snooze as snooze_module

    full_id = _run_service(services.resolve_thread_id, thread_id, email) or thread_id
    _, snooze_until = snooze_module.snooze_item(
        entity_type="thread", entity_id=full_id, until=until, source_id=email
    )
    print(f"snoozed until {snooze_until.strftime('%Y-%m-%d %H:%M')}")


@cli("life comms email", name="senders")
def senders(limit: int = 20):
    """Show sender statistics"""
    from .comms import senders as senders_module

    top = senders_module.get_top_senders(limit=limit)
    if not top:
        print("no sender data yet")
        return
    for s in top:
        resp = f"{s.response_rate:.0%}" if s.received_count > 0 else "n/a"
        print(
            f"  {s.sender[:30]:30} | recv:{s.received_count:3} resp:{resp:4} pri:{s.priority_score:.2f}"
        )


@cli("life comms email", name="rules")
def rules():
    """Show triage rules"""
    from .comms.config import RULES_PATH

    if not RULES_PATH.exists():
        print(f"no rules file — create at: {RULES_PATH}")
        return
    print(RULES_PATH.read_text())


@cli("life comms email", name="contacts")
def contacts():
    """Show contact notes"""
    from .comms.contacts import CONTACTS_PATH, get_all_contacts

    if not CONTACTS_PATH.exists():
        print(f"no contacts file — create at: {CONTACTS_PATH}")
        return
    for c in get_all_contacts():
        tags = f" [{', '.join(c.tags)}]" if c.tags else ""
        print(f"{c.pattern}{tags}\n  {c.notes}\n")

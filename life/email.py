"""life email — email commands."""

from __future__ import annotations

from typing import Any

from fncli import cli

from .lib.errors import echo, exit_error


def _run_service(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ValueError as exc:
        exit_error(str(exc))


@cli("life email", name="inbox")
def inbox(limit: int = 20):
    """Unified inbox"""
    from datetime import datetime

    from .comms.services import get_unified_inbox

    items = get_unified_inbox(limit=limit)
    if not items:
        echo("inbox empty")
        return
    for item in items:
        ts = datetime.fromtimestamp(item.timestamp / 1000).strftime("%m-%d %H:%M")
        unread = "●" if item.unread else " "
        echo(f"{unread} [{ts}] {item.sender[:25]:25} {item.preview}")


@cli("life email", name="triage")
def triage(limit: int = 20, confidence: float = 0.7, dry_run: bool = False, execute: bool = False):
    """Triage inbox — Claude bulk-proposes actions"""
    from .comms import triage as triage_module
    from .comms.services import execute_approved_proposals

    echo("scanning inbox...")
    proposals = triage_module.triage_inbox(limit=limit)
    if not proposals:
        echo("nothing to triage")
        return

    echo(f"\n{len(proposals)} proposals:\n")
    for p in proposals:
        conf = f"{p.confidence:.0%}"
        skip = " (skip)" if p.confidence < confidence or p.action == "ignore" else ""
        echo(f"  [{conf}] {p.action:10} {p.item.sender[:20]:20} {p.reasoning}{skip}")

    created = triage_module.create_proposals_from_triage(
        proposals, min_confidence=confidence, dry_run=dry_run
    )

    if dry_run:
        echo(f"\ndry run: would create {len(created)} proposals")
        return

    echo(f"\ncreated {len(created)} proposals")

    if execute and created:
        echo("\nexecuting...")
        results = execute_approved_proposals()
        executed = sum(1 for r in results if r.success)
        echo(f"executed: {executed}/{len(results)}")


@cli("life email", name="clear")
def clear(limit: int = 50, confidence: float = 0.8, dry_run: bool = False):
    """One-command inbox clear: triage → approve → execute"""
    from .comms import proposals as proposals_module
    from .comms import triage as triage_module
    from .comms.contacts import get_high_priority_patterns
    from .comms.services import execute_approved_proposals

    echo("scanning inbox...")
    proposals = triage_module.triage_inbox(limit=limit)
    if not proposals:
        echo("inbox clear")
        return

    high_priority = get_high_priority_patterns()

    def _is_high_priority(p) -> bool:
        return any(pat in p.item.sender.lower() for pat in high_priority)

    auto = [
        p
        for p in proposals
        if p.confidence >= confidence and p.action != "ignore" and not _is_high_priority(p)
    ]
    review = [
        p
        for p in proposals
        if p.confidence < confidence or p.action == "ignore" or _is_high_priority(p)
    ]

    echo(f"\nauto ({len(auto)}) | review ({len(review)})\n")
    for p in auto:
        echo(f"  {p.action:8} {p.item.sender[:25]:25} {p.reasoning[:30]}")

    if review:
        echo("\nneeds review:")
        for p in review:
            echo(f"  [{p.confidence:.0%}] {p.item.sender[:25]:25} {p.item.preview[:30]}")

    if dry_run:
        echo(f"\ndry run: would auto-execute {len(auto)} items")
        return

    created = triage_module.create_proposals_from_triage(auto, min_confidence=0.0, dry_run=False)
    for pid, _ in created:
        proposals_module.approve_proposal(pid)

    results = execute_approved_proposals()
    executed = sum(1 for r in results if r.success)
    echo(f"\nexecuted: {executed}/{len(results)}")
    if review:
        echo(f"run `life email review` for {len(review)} items needing attention")


@cli("life email", name="threads")
def threads(label: str = "inbox"):
    """List threads"""
    from .comms import services

    for entry in services.list_threads(label):
        acct = entry["account"]
        thread_list = entry["threads"]
        echo(f"\n{acct['email']} ({label}):")
        if not thread_list:
            echo("  no threads")
            continue
        for t in thread_list:
            date_str = t.get("date", "")[:16]
            echo(f"  {t['id'][:8]} | {date_str:16} | {t['snippet'][:50]}")


@cli("life email", name="thread")
def thread(thread_id: str, email: str | None = None):
    """Fetch and display full thread"""
    from .comms import services

    full_id = _run_service(services.resolve_thread_id, thread_id, email) or thread_id
    messages = _run_service(services.fetch_thread, full_id, email)
    echo(f"\nThread: {messages[0]['subject']}")
    echo("=" * 80)
    for msg in messages:
        echo(f"\nFrom: {msg['from']}")
        echo(f"Date: {msg['date']}")
        echo(f"\n{msg['body']}\n")
        echo("-" * 80)


@cli("life email", name="summarize")
def summarize(thread_id: str, email: str | None = None):
    """Summarize thread using Claude"""
    from .comms import claude, services

    full_id = _run_service(services.resolve_thread_id, thread_id, email) or thread_id
    messages = _run_service(services.fetch_thread, full_id, email)
    echo(f"summarizing {len(messages)} messages...")
    echo(f"\n{claude.summarize_thread(messages)}")


@cli("life email", name="compose")
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
    echo(f"draft {draft_id[:8]} — from {from_addr} to {to}")
    echo(f"run `life email approve {draft_id[:8]}` to approve")


@cli("life email", name="reply")
def reply(thread_id: str, body: str | None = None, email: str | None = None, all: bool = False):
    """Reply to thread"""
    if not body:
        exit_error("--body required")
    from .comms.services import reply_to_thread

    draft_id, to_addr, _subject, _cc = _run_service(
        reply_to_thread, thread_id=thread_id, body=body, email=email, reply_all=all
    )
    echo(f"reply draft {draft_id[:8]} → {to_addr}")
    echo(f"run `life email approve {draft_id[:8]}` to approve")


@cli("life email", name="draft-reply")
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
    echo("generating draft...")
    body, reasoning = claude.generate_reply(context, instructions)
    if not body:
        exit_error(f"failed: {reasoning}")

    draft_id, to_addr, subject, _cc = _run_service(
        services.reply_to_thread, thread_id=full_id, body=body, email=email, reply_all=all
    )
    echo(f"\nreasoning: {reasoning}")
    echo(f"\ndraft {draft_id[:8]} → {to_addr}  |  {subject}")
    echo(f"\n{body}\n")
    echo(f"run `life email approve {draft_id[:8]}` to approve")


@cli("life email", name="drafts")
def drafts_list():
    """List pending drafts"""
    from .comms.drafts import list_pending_drafts

    pending = list_pending_drafts()
    if not pending:
        echo("no pending drafts")
        return
    for d in pending:
        status = "✓ approved" if d.approved_at else "⧗ pending"
        echo(f"  {d.id[:8]} | {d.to_addr} | {d.subject or '(no subject)'} | {status}")


@cli("life email", name="draft")
def draft_show(draft_id: str):
    """Show draft details"""
    from .comms.drafts import get_draft

    d = get_draft(draft_id)
    if not d:
        exit_error(f"draft {draft_id} not found")
    echo(f"To: {d.to_addr}")
    if d.cc_addr:
        echo(f"Cc: {d.cc_addr}")
    echo(f"Subject: {d.subject or '(no subject)'}")
    echo(f"\n{d.body}\n")
    if d.claude_reasoning:
        echo(f"--- reasoning ---\n{d.claude_reasoning}")


@cli("life email", name="approve")
def approve_draft(draft_id: str):
    """Approve draft for sending"""
    from .comms import drafts as drafts_module
    from .comms import policy

    full_id = drafts_module.resolve_draft_id(draft_id) or draft_id
    d = drafts_module.get_draft(full_id)
    if not d:
        exit_error(f"draft {draft_id} not found")
    if d.approved_at:
        echo("already approved")
        return
    allowed, err = policy.check_recipient_allowed(d.to_addr)
    if not allowed:
        exit_error(f"cannot approve: {err}")
    drafts_module.approve_draft(full_id)
    echo(f"approved {full_id[:8]} — run `life email send {full_id[:8]}` to send")


@cli("life email", name="send")
def send_draft(draft_id: str):
    """Send approved draft"""
    from .comms import drafts as drafts_module
    from .comms import services

    full_id = drafts_module.resolve_draft_id(draft_id) or draft_id
    d = drafts_module.get_draft(full_id)
    if not d:
        exit_error(f"draft {draft_id} not found")
    _run_service(services.send_draft, full_id)
    echo(f"sent → {d.to_addr}  |  {d.subject}")


@cli("life email", name="archive")
def archive(thread_id: str, email: str | None = None):
    """Archive thread"""
    from .comms import audit, services

    _run_service(services.thread_action, "archive", thread_id, email)
    audit.log("archive", "thread", thread_id, {"reason": "manual"})
    echo(f"archived {thread_id}")


@cli("life email", name="delete")
def delete(thread_id: str, email: str | None = None):
    """Delete thread"""
    from .comms import audit, services

    _run_service(services.thread_action, "delete", thread_id, email)
    audit.log("delete", "thread", thread_id, {"reason": "manual"})
    echo(f"deleted {thread_id}")


@cli("life email", name="flag")
def flag(thread_id: str, email: str | None = None):
    """Flag thread"""
    from .comms import audit, services

    _run_service(services.thread_action, "flag", thread_id, email)
    audit.log("flag", "thread", thread_id, {"reason": "manual"})
    echo(f"flagged {thread_id}")


@cli("life email", name="snooze")
def snooze(thread_id: str, until: str = "tomorrow", email: str | None = None):
    """Snooze thread"""
    from .comms import services
    from .comms import snooze as snooze_module

    full_id = _run_service(services.resolve_thread_id, thread_id, email) or thread_id
    _, snooze_until = snooze_module.snooze_item(
        entity_type="thread", entity_id=full_id, until=until, source_id=email
    )
    echo(f"snoozed until {snooze_until.strftime('%Y-%m-%d %H:%M')}")


@cli("life email", name="review")
def review(action: str | None = None):
    """Review proposals"""
    from .comms import proposals as proposals_module

    items = proposals_module.list_proposals(status="pending")
    if action:
        items = [p for p in items if p["proposed_action"] == action]
    if not items:
        echo("no proposals")
        return
    by_action: dict[str, list[Any]] = {}
    for p in items:
        by_action.setdefault(p["proposed_action"], []).append(p)
    for act in ["flag", "archive", "delete"]:
        if act not in by_action:
            continue
        echo(f"\n{act.upper()} ({len(by_action[act])}):")
        for p in by_action[act]:
            echo(f"  {p['id'][:8]} | {p['agent_reasoning'] or p['entity_id'][:8]}")


@cli("life email", name="approve-proposal")
def approve_proposal(proposal_id: str | None = None, action: str | None = None, all: bool = False):
    """Approve proposal(s)"""
    from .comms import proposals as proposals_module

    if all or action:
        pending = proposals_module.list_proposals(status="pending")
        if action:
            pending = [p for p in pending if p["proposed_action"] == action]
        count = sum(1 for p in pending if proposals_module.approve_proposal(p["id"]))
        echo(f"approved {count} proposals")
        return
    if not proposal_id:
        exit_error("provide proposal_id or --all")
    if proposals_module.approve_proposal(proposal_id):
        echo(f"approved {proposal_id[:8]}")
    else:
        exit_error("not found or already processed")


@cli("life email", name="resolve")
def resolve():
    """Execute all approved proposals"""
    from .comms import proposals as proposals_module
    from .comms import services

    approved = proposals_module.get_approved_proposals()
    if not approved:
        echo("no approved proposals")
        return
    results = services.execute_approved_proposals()
    executed = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)
    echo(f"executed: {executed}  failed: {failed}")


@cli("life email", name="senders")
def senders(limit: int = 20):
    """Show sender statistics"""
    from .comms import senders as senders_module

    top = senders_module.get_top_senders(limit=limit)
    if not top:
        echo("no sender data yet")
        return
    for s in top:
        resp = f"{s.response_rate:.0%}" if s.received_count > 0 else "n/a"
        echo(
            f"  {s.sender[:30]:30} | recv:{s.received_count:3} resp:{resp:4} pri:{s.priority_score:.2f}"
        )


@cli("life email", name="stats")
def stats():
    """Show learning stats"""
    from .comms import learning

    action_stats = learning.get_decision_stats()
    if not action_stats:
        echo("no decision data yet")
        return
    for action, s in sorted(action_stats.items(), key=lambda x: -x[1].total):
        echo(f"  {action:12} | {s.total:3} total | {s.accuracy:.0%} accuracy")


@cli("life email", name="digest")
def digest(days: int = 7):
    """Weekly activity digest"""
    from .comms import digest as digest_module

    echo(digest_module.format_digest(digest_module.get_digest(days=days)))


@cli("life email", name="rules")
def rules():
    """Show triage rules"""
    from .comms.config import RULES_PATH

    if not RULES_PATH.exists():
        echo(f"no rules file — create at: {RULES_PATH}")
        return
    echo(RULES_PATH.read_text())


@cli("life email", name="contacts")
def contacts():
    """Show contact notes"""
    from .comms.contacts import CONTACTS_PATH, get_all_contacts

    if not CONTACTS_PATH.exists():
        echo(f"no contacts file — create at: {CONTACTS_PATH}")
        return
    for c in get_all_contacts():
        tags = f" [{', '.join(c.tags)}]" if c.tags else ""
        echo(f"{c.pattern}{tags}\n  {c.notes}\n")

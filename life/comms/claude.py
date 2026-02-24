"""Headless Claude invocation for draft generation and summarization."""

import subprocess
from typing import Any

from .contacts import get_contact_context


def _extract_sender_from_context(context: str) -> str:
    for line in context.split("\n"):
        if line.startswith("From:"):
            return line[5:].strip()
    return ""


def generate_reply(
    thread_context: str,
    instructions: str | None = None,
    model: str = "claude-sonnet-4-20250514",
) -> tuple[str, str]:
    """Generate reply draft using headless Claude.

    Returns (draft_body, reasoning).
    """
    sender = _extract_sender_from_context(thread_context)
    contact = get_contact_context(sender) if sender else None
    contact_info = ""
    if contact:
        tags = f" [{', '.join(contact.tags)}]" if contact.tags else ""
        contact_info = f"\nCONTACT NOTES{tags}: {contact.notes}"

    prompt = f"""You are drafting an email reply. Be concise and professional.

THREAD CONTEXT:
{thread_context}
{contact_info}

{f"INSTRUCTIONS: {instructions}" if instructions else ""}

OUTPUT FORMAT:
First line: Your reasoning (1 sentence)
Then a blank line
Then the reply body (no greeting, no signature - those are added automatically)

Example:
Acknowledging their update and confirming next steps.

Thanks for the update. I'll review the proposal by Friday and get back to you with feedback."""

    result = subprocess.run(
        [
            "claude",
            "--print",
            "--model",
            model,
            "-p",
            prompt,
            "--dangerously-skip-permissions",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        return "", f"Claude failed: {result.stderr}"

    output = result.stdout.strip()
    if not output:
        return "", "No output from Claude"

    parts = output.split("\n\n", 1)
    if len(parts) == 2:
        reasoning, body = parts
    else:
        reasoning = ""
        body = output

    return body.strip(), reasoning.strip()


def generate_signal_reply(
    conversation: list[dict[str, Any]],
    instructions: str | None = None,
    model: str = "claude-sonnet-4-20250514",
) -> tuple[str, str]:
    """Generate Signal reply using headless Claude.

    Returns (reply_text, reasoning).
    """
    context_lines = []
    last_sender = ""
    for msg in conversation[-10:]:
        sender = msg.get("sender_name") or msg.get("sender_phone", "Unknown")
        last_sender = sender
        body = msg.get("body", "")
        context_lines.append(f"{sender}: {body}")

    context = "\n".join(context_lines)

    contact = get_contact_context(last_sender) if last_sender else None
    contact_info = ""
    if contact:
        tags = f" [{', '.join(contact.tags)}]" if contact.tags else ""
        contact_info = f"\nCONTACT NOTES{tags}: {contact.notes}"

    prompt = f"""You are replying to a Signal message. Be casual and brief.

CONVERSATION:
{context}
{contact_info}
{f"INSTRUCTIONS: {instructions}" if instructions else ""}

OUTPUT FORMAT:
First line: Your reasoning (1 sentence)
Then a blank line
Then your reply (1-3 sentences max, casual tone)

Example:
Confirming the time works.

Yeah 3pm works for me, see you then!"""

    result = subprocess.run(
        [
            "claude",
            "--print",
            "--model",
            model,
            "-p",
            prompt,
            "--dangerously-skip-permissions",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        return "", f"Claude failed: {result.stderr}"

    output = result.stdout.strip()
    if not output:
        return "", "No output from Claude"

    parts = output.split("\n\n", 1)
    if len(parts) == 2:
        reasoning, body = parts
    else:
        reasoning = ""
        body = output

    return body.strip(), reasoning.strip()


def summarize_thread(
    messages: list[dict[str, Any]],
    model: str = "claude-haiku-4-5",
) -> str:
    """Summarize an email thread. Returns summary string."""
    context_lines = []
    for msg in messages:
        context_lines.append(f"From: {msg.get('from', 'Unknown')}")
        context_lines.append(f"Date: {msg.get('date', '')}")
        body = msg.get("body", "")[:1000]
        context_lines.append(f"Body: {body}")
        context_lines.append("---")

    context = "\n".join(context_lines)

    prompt = f"""Summarize this email thread in 2-3 sentences. Focus on:
- What is being discussed/requested
- Current status (waiting on response? resolved? action needed?)
- Key people involved

THREAD:
{context}

Respond with just the summary, no preamble."""

    result = subprocess.run(
        [
            "claude",
            "--print",
            "--model",
            model,
            "-p",
            prompt,
            "--dangerously-skip-permissions",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        return f"Summary failed: {result.stderr}"

    return result.stdout.strip()

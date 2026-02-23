"""Agent bus — parse Signal messages as commands, execute, respond."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Any

from .config import COMMS_DIR

AUTHORIZED_FILE = COMMS_DIR / "authorized_senders.txt"


@dataclass
class Command:
    action: str
    args: list[str]
    raw: str


@dataclass
class CommandResult:
    success: bool
    message: str
    executed: str


def get_authorized_senders() -> set[str]:
    if not AUTHORIZED_FILE.exists():
        return set()
    lines = AUTHORIZED_FILE.read_text().strip().split("\n")
    return {line.strip() for line in lines if line.strip() and not line.startswith("#")}


def add_authorized_sender(phone: str) -> None:
    COMMS_DIR.mkdir(exist_ok=True)
    senders = get_authorized_senders()
    senders.add(phone)
    AUTHORIZED_FILE.write_text("\n".join(sorted(senders)) + "\n")


def remove_authorized_sender(phone: str) -> bool:
    senders = get_authorized_senders()
    if phone not in senders:
        return False
    senders.discard(phone)
    AUTHORIZED_FILE.write_text("\n".join(sorted(senders)) + "\n")
    return True


def is_command(text: str) -> bool:
    text = text.strip().lower()
    return text.startswith(("!", "comms "))


def parse_command(text: str) -> Command | None:
    text = text.strip()
    if not is_command(text):
        return None

    if text.startswith("!"):
        text = text[1:]
    elif text.lower().startswith("comms "):
        text = text[6:]

    parts = text.split()
    if not parts:
        return None

    action = parts[0].lower()
    args = parts[1:]

    return Command(action=action, args=args, raw=text)


COMMAND_MAP = {
    "inbox": "comms inbox -n 5",
    "status": "comms status",
    "triage": "comms triage --dry-run -n 10",
    "clear": "comms clear --dry-run",
    "stats": "comms stats",
    "senders": "comms senders -n 10",
    "threads": "comms threads -l inbox",
    "accounts": "comms accounts",
    "review": "comms review",
    "resolve": "comms resolve",
    "drafts": "comms drafts",
    "contacts": "comms contacts",
    "rules": "comms rules",
    "help": None,
}


def parse_natural_language(text: str) -> Command | None:
    import json

    prompt = f"""Parse this message into a comms command. Return JSON only.

AVAILABLE COMMANDS:
- inbox: show unified inbox
- status: show system status
- triage: AI triage inbox (preview)
- clear: auto-clear inbox (preview)
- threads: list email threads
- accounts: list accounts
- review: show pending proposals
- resolve: execute approved proposals
- drafts: show pending drafts
- senders: show sender statistics
- draft <thread_id>: generate reply draft for thread
- approve <draft_id>: approve a draft
- send <draft_id>: send approved draft
- summarize <thread_id>: summarize a thread
- archive <id>: archive thread
- delete <id>: delete thread
- ping: test connection
- help: show commands

MESSAGE: {text}

OUTPUT FORMAT (JSON only, no explanation):
{{"action": "command_name", "args": ["arg1", "arg2"]}}

If not a command request, return: {{"action": null}}"""

    try:
        result = subprocess.run(
            [
                "claude",
                "--print",
                "--model",
                "claude-haiku-4-5",
                "-p",
                prompt,
                "--dangerously-skip-permissions",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None

        output = result.stdout.strip()
        if output.startswith("```"):
            lines = output.split("\n")
            output = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

        data = json.loads(output)
        if not data.get("action"):
            return None

        return Command(
            action=data["action"],
            args=data.get("args", []),
            raw=text,
        )
    except Exception:
        return None


def _run_comms_command(cmd: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            cmd.split(),
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = result.stdout.strip() or result.stderr.strip()
        return result.returncode == 0, output[:500]
    except subprocess.TimeoutExpired:
        return False, "Command timed out"
    except Exception as e:
        return False, str(e)


def execute_command(cmd: Command) -> CommandResult:
    action = cmd.action

    if action == "help":
        help_text = "Commands: " + ", ".join(sorted(COMMAND_MAP.keys()))
        return CommandResult(success=True, message=help_text, executed="help")

    if action == "ping":
        return CommandResult(success=True, message="pong", executed="ping")

    if action in COMMAND_MAP:
        comms_cmd = COMMAND_MAP[action]
        if comms_cmd is None:
            return CommandResult(
                success=False, message=f"No command mapped for: {action}", executed=action
            )
        success, output = _run_comms_command(comms_cmd)
        return CommandResult(success=success, message=output, executed=comms_cmd)

    if action == "archive" and cmd.args:
        thread_id = cmd.args[0]
        success, output = _run_comms_command(f"comms archive {thread_id}")
        return CommandResult(
            success=success,
            message=output or f"Archived {thread_id}",
            executed=f"archive {thread_id}",
        )

    if action == "delete" and cmd.args:
        thread_id = cmd.args[0]
        success, output = _run_comms_command(f"comms delete {thread_id}")
        return CommandResult(
            success=success,
            message=output or f"Deleted {thread_id}",
            executed=f"delete {thread_id}",
        )

    if action == "draft" and cmd.args:
        thread_id = cmd.args[0]
        success, output = _run_comms_command(f"comms draft-reply {thread_id}")
        return CommandResult(
            success=success,
            message=output,
            executed=f"draft-reply {thread_id}",
        )

    if action == "summarize" and cmd.args:
        thread_id = cmd.args[0]
        success, output = _run_comms_command(f"comms summarize {thread_id}")
        return CommandResult(
            success=success,
            message=output,
            executed=f"summarize {thread_id}",
        )

    if action == "approve" and cmd.args:
        draft_id = cmd.args[0]
        success, output = _run_comms_command(f"comms approve-draft {draft_id}")
        return CommandResult(
            success=success,
            message=output or f"Approved {draft_id}",
            executed=f"approve-draft {draft_id}",
        )

    if action == "send" and cmd.args:
        draft_id = cmd.args[0]
        success, output = _run_comms_command(f"comms send {draft_id}")
        return CommandResult(
            success=success,
            message=output or f"Sent {draft_id}",
            executed=f"send {draft_id}",
        )

    return CommandResult(success=False, message=f"Unknown command: {action}", executed=action)


def process_message(
    phone: str, sender: str, body: str, use_nlp: bool = False
) -> CommandResult | None:
    authorized = get_authorized_senders()
    if authorized and sender not in authorized:
        return None

    cmd = None
    if is_command(body):
        cmd = parse_command(body)
    elif use_nlp:
        cmd = parse_natural_language(body)

    if not cmd:
        return None

    return execute_command(cmd)


def handle_incoming(phone: str, message: dict[str, Any], use_nlp: bool = False) -> str | None:
    sender = message.get("sender_phone", "")
    body = message.get("body", "")

    result = process_message(phone, sender, body, use_nlp=use_nlp)
    if not result:
        return None

    return result.message

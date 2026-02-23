import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from fncli import cli

from .lib.errors import echo, exit_error

SIGNAL_CLI = "signal-cli"
PEOPLE_DIR = Path.home() / "life" / "steward" / "people"


def _default_account() -> str | None:
    result = subprocess.run(
        [SIGNAL_CLI, "listAccounts"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        return None
    for line in result.stdout.strip().split("\n"):
        if line.startswith("Number: "):
            return line.replace("Number: ", "").strip()
    return None


def resolve_contact(name_or_number: str) -> str:
    if name_or_number.startswith("+") or name_or_number.lstrip("0").isdigit():
        return name_or_number

    if not PEOPLE_DIR.exists():
        return name_or_number

    name_lower = name_or_number.lower()
    for profile in PEOPLE_DIR.glob("*.md"):
        text = profile.read_text()
        match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
        if not match:
            continue
        try:
            frontmatter = yaml.safe_load(match.group(1))
        except Exception:  # noqa: S112
            continue
        if not isinstance(frontmatter, dict):
            continue
        signal_num = frontmatter.get("signal")
        if not signal_num:
            continue
        if profile.stem.lower() == name_lower:
            return str(signal_num)
        name_field = frontmatter.get("name", "")
        if isinstance(name_field, str) and name_field.lower() == name_lower:
            return str(signal_num)

    return name_or_number


def send(recipient: str, message: str, attachment: str | None = None) -> tuple[bool, str]:
    phone = _default_account()
    if not phone:
        return False, "no Signal account registered with signal-cli"

    cmd = [SIGNAL_CLI, "-a", phone, "send"]
    if attachment:
        cmd.extend(["--attachment", attachment])
    cmd.extend(["-m", message, recipient])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode == 0:
        return True, "sent"
    return False, result.stderr.strip() or "send failed"


def send_to(
    phone: str, recipient: str, message: str, attachment: str | None = None
) -> tuple[bool, str]:
    cmd = [SIGNAL_CLI, "-a", phone, "send"]
    if attachment:
        cmd.extend(["--attachment", attachment])
    cmd.extend(["-m", message, recipient])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode == 0:
        return True, "sent"
    return False, result.stderr.strip() or "send failed"


def send_group(phone: str, group_id: str, message: str) -> tuple[bool, str]:
    result = subprocess.run(
        [SIGNAL_CLI, "-a", phone, "send", "-m", message, "-g", group_id],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode == 0:
        return True, "sent to group"
    return False, result.stderr.strip() or "send failed"


def receive(
    timeout: int = 5, phone: str | None = None, store: bool = False
) -> list[dict[str, Any]]:
    acct = phone or _default_account()
    if not acct:
        return []

    result = subprocess.run(
        [SIGNAL_CLI, "-a", acct, "receive", "-t", str(timeout)],
        capture_output=True,
        text=True,
        timeout=timeout + 30,
    )
    if result.returncode != 0:
        return []

    messages = []
    output = result.stdout + result.stderr

    envelope_pattern = re.compile(r'Envelope from: "([^"]*)" (\+\d+)', re.MULTILINE)
    body_pattern = re.compile(r"^Body: (.+)$", re.MULTILINE)
    timestamp_pattern = re.compile(r"^Timestamp: (\d+)", re.MULTILINE)

    blocks = re.split(r"\n(?=Envelope from:)", output)
    for block in blocks:
        envelope_match = envelope_pattern.search(block)
        body_match = body_pattern.search(block)
        timestamp_match = timestamp_pattern.search(block)
        if envelope_match and body_match:
            messages.append(
                {
                    "id": timestamp_match.group(1) if timestamp_match else "",
                    "from": envelope_match.group(2),
                    "from_name": envelope_match.group(1),
                    "body": body_match.group(1),
                    "timestamp": int(timestamp_match.group(1)) if timestamp_match else 0,
                    "group": None,
                }
            )

    if store and messages and acct:
        _store_messages(acct, messages)

    return messages


def _store_messages(phone: str, messages: list[dict[str, Any]]) -> int:
    from .comms.db import get_db

    stored = 0
    with get_db() as conn:
        for msg in messages:
            try:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO signal_messages
                    (id, account_phone, sender_phone, sender_name, body, timestamp, group_id, received_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        msg["id"],
                        phone,
                        msg["from"],
                        msg.get("from_name", ""),
                        msg["body"],
                        msg["timestamp"],
                        msg.get("group"),
                        datetime.now().isoformat(),
                    ),
                )
                stored += 1
            except Exception:  # noqa: S110
                pass
    return stored


def get_messages(
    phone: str | None = None,
    sender: str | None = None,
    limit: int = 50,
    unread_only: bool = False,
) -> list[dict[str, Any]]:
    from .comms.db import get_db

    query = "SELECT * FROM signal_messages WHERE 1=1"
    params: list[Any] = []
    if phone:
        query += " AND account_phone = ?"
        params.append(phone)
    if sender:
        query += " AND sender_phone = ?"
        params.append(sender)
    if unread_only:
        query += " AND read_at IS NULL"
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


def get_conversations(phone: str) -> list[dict[str, Any]]:
    from .comms.db import get_db

    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT sender_phone, sender_name,
                   COUNT(*) as message_count,
                   MAX(timestamp) as last_timestamp,
                   SUM(CASE WHEN read_at IS NULL THEN 1 ELSE 0 END) as unread_count
            FROM signal_messages
            WHERE account_phone = ?
            GROUP BY sender_phone
            ORDER BY last_timestamp DESC
            """,
            (phone,),
        ).fetchall()
        return [dict(row) for row in rows]


def mark_read(message_id: str) -> bool:
    from .comms.db import get_db

    with get_db() as conn:
        conn.execute(
            "UPDATE signal_messages SET read_at = ? WHERE id = ?",
            (datetime.now().isoformat(), message_id),
        )
    return True


def get_message(message_id: str) -> dict[str, Any] | None:
    from .comms.db import get_db

    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM signal_messages WHERE id = ? OR id LIKE ?",
            (message_id, f"{message_id}%"),
        ).fetchone()
        return dict(row) if row else None


def reply_to(phone: str, message_id: str, body: str) -> tuple[bool, str, dict[str, Any] | None]:
    msg = get_message(message_id)
    if not msg:
        return False, f"message {message_id} not found", None
    success, result = send_to(phone, msg["sender_phone"], body)
    if success:
        mark_read(msg["id"])
    return success, result, msg


def list_accounts() -> list[str]:
    result = subprocess.run(
        [SIGNAL_CLI, "listAccounts"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        return []
    return [
        line.replace("Number: ", "").strip()
        for line in result.stdout.strip().split("\n")
        if line.startswith("Number: ")
    ]


def list_contacts_for(phone: str) -> list[dict[str, Any]]:
    result = _run(["listContacts"], phone)
    if not result or not isinstance(result, list):
        return []
    return [
        {"number": c.get("number", ""), "name": c.get("name", "")}
        for c in result
        if c.get("number")
    ]


def list_groups(phone: str) -> list[dict[str, Any]]:
    result = _run(["listGroups"], account=phone)
    if not result or not isinstance(result, list):
        return []
    return [{"id": g.get("id", ""), "name": g.get("name", "")} for g in result]


def test_connection(phone: str) -> tuple[bool, str]:
    if phone not in list_accounts():
        return False, "account not registered"
    result = _run(["getUserStatus", phone], account=phone)
    if result is None:
        return False, "failed to get user status"
    return True, "connected"


def link_device(device_name: str = "life-cli") -> tuple[bool, str]:
    import io

    import qrcode

    process = subprocess.Popen(
        [SIGNAL_CLI, "link", "-n", device_name],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    uri = None
    if process.stdout:
        for line in iter(process.stdout.readline, ""):
            line = line.strip()
            if line.startswith(("sgnl://", "tsdevice:")):
                uri = line
                break

    if not uri:
        process.terminate()
        stderr = process.stderr.read() if process.stderr else ""
        return False, f"no device URI received. stderr: {stderr}"

    qr = qrcode.QRCode(border=1)
    qr.add_data(uri)
    qr.make()
    f = io.StringIO()
    qr.print_ascii(out=f, invert=True)
    print(f.getvalue())  # noqa: T201

    try:
        process.wait(timeout=120)
        if process.returncode == 0:
            return True, "linked successfully"
        return False, (process.stderr.read() if process.stderr else "") or "link failed"
    except subprocess.TimeoutExpired:
        process.terminate()
        return False, "timeout waiting for scan"


def _run(args: list[str], account: str | None = None) -> dict[str, Any] | list[Any] | None:
    cmd = [SIGNAL_CLI]
    if account:
        cmd.extend(["-a", account])
    cmd.extend(args)
    cmd.extend(["--output=json"])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return None
        if not result.stdout.strip():
            return {}
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        return None


def list_contacts() -> list[dict[str, Any]]:
    phone = _default_account()
    if not phone:
        return []
    return list_contacts_for(phone)


@cli("life signal", name="send")
def send_cmd(
    recipient: str,
    message: str,
    attachment: str | None = None,
):
    """Send a Signal message to a contact or number"""
    number = resolve_contact(recipient)
    success, result = send(number, message, attachment=attachment)
    if success:
        display = recipient if number == recipient else f"{recipient} ({number})"
        echo(f"sent → {display}")
    else:
        exit_error(f"failed: {result}")


@cli("life signal", name="check")
def check(timeout: int = 5):
    """Pull and display recent Signal messages"""
    messages = receive(timeout=timeout)
    if not messages:
        echo("no new messages")
        return
    for msg in messages:
        sender = msg.get("from_name") or msg.get("from", "?")
        echo(f"{sender}: {msg['body']}")


@cli("life signal", name="receive")
def receive_cmd(timeout: int = 5):
    """Receive and store Signal messages"""
    phone = _default_account()
    if not phone:
        exit_error("no Signal account registered")
    msgs = receive(timeout=timeout, phone=phone, store=True)
    if not msgs:
        echo("no new messages")
        return
    echo(f"received {len(msgs)} message(s)")
    for msg in msgs:
        sender = msg.get("from_name") or msg.get("from", "?")
        echo(f"  {sender}: {msg['body']}")


@cli("life signal", name="inbox")
def signal_inbox():
    """Show Signal conversations"""
    phone = _default_account()
    if not phone:
        exit_error("no Signal account registered")
    conversations = get_conversations(phone)
    if not conversations:
        echo("no conversations — run `life signal receive` first")
        return
    for c in conversations:
        name = c["sender_name"] or c["sender_phone"]
        unread = f" ({c['unread_count']} unread)" if c["unread_count"] else ""
        echo(f"  {c['sender_phone']:16} | {name:20} | {c['message_count']} msgs{unread}")


@cli("life signal", name="history")
def signal_history(contact: str, limit: int = 20):
    """Show message history with a contact"""
    phone = _default_account()
    if not phone:
        exit_error("no Signal account registered")
    msgs = get_messages(phone=phone, sender=contact, limit=limit)
    if not msgs:
        echo(f"no messages from {contact}")
        return
    for msg in reversed(msgs):
        sender = msg["sender_name"] or msg["sender_phone"]
        ts = datetime.fromtimestamp(msg["timestamp"] / 1000).strftime("%m-%d %H:%M")
        mid = msg["id"][:8] if msg.get("id") else ""
        echo(f"{mid} [{ts}] {sender}: {msg['body']}")


@cli("life signal", name="reply")
def reply_cmd(message_id: str, message: str):
    """Reply to a Signal message"""
    phone = _default_account()
    if not phone:
        exit_error("no Signal account registered")
    success, err, original = reply_to(phone, message_id, message)
    if success and original:
        sender = original["sender_name"] or original["sender_phone"]
        echo(f"replied to {sender}")
    else:
        exit_error(f"failed: {err}")


@cli("life signal", name="status")
def status():
    """Show registered Signal accounts"""
    accounts = list_accounts()
    if not accounts:
        echo("no Signal accounts — run: signal-cli link")
        return
    for account in accounts:
        echo(account)


@cli("life signal", name="contacts")
def contacts_cmd():
    """List Signal contacts"""
    phone = _default_account()
    if not phone:
        exit_error("no Signal account registered")
    contacts = list_contacts_for(phone)
    if not contacts:
        echo("no contacts")
        return
    for c in contacts:
        echo(f"  {c['number']:20} {c.get('name', '')}")


@cli("life signal", name="groups")
def groups_cmd():
    """List Signal groups"""
    phone = _default_account()
    if not phone:
        exit_error("no Signal account registered")
    groups = list_groups(phone)
    if not groups:
        echo("no groups")
        return
    for g in groups:
        echo(f"  {g['id'][:16]} | {g['name']}")

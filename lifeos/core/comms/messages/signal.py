import io
import json
import logging
import re
import subprocess
from datetime import datetime
from typing import Any

import qrcode

from lifeos.core.comms import events
from lifeos.core.lib.resolve import resolve_people_field
from lifeos.core.lib.store import get_db

logger = logging.getLogger(__name__)

SIGNAL_CLI = "signal-cli"


def default_account() -> str | None:
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
    result = resolve_people_field(name_or_number, "signal")
    return result or name_or_number


def send(recipient: str, message: str, attachment: str | None = None) -> tuple[bool, str]:
    phone = default_account()
    if not phone:
        return False, "no Signal account registered with signal-cli"
    return send_to(phone, recipient, message, attachment=attachment)


def send_to(phone: str, recipient: str, message: str, attachment: str | None = None) -> tuple[bool, str]:
    cmd = [SIGNAL_CLI, "-a", phone, "send"]
    if attachment:
        cmd.extend(["--attachment", attachment])
    cmd.extend(["-m", message, recipient])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    success = result.returncode == 0
    _track_outbound(recipient, message, success=success)
    if success:
        return True, "sent"
    return False, result.stderr.strip() or "send failed"


def send_group(phone: str, group_id: str, message: str) -> tuple[bool, str]:
    result = subprocess.run(
        [SIGNAL_CLI, "-a", phone, "send", "-m", message, "-g", group_id],
        capture_output=True,
        text=True,
        timeout=30,
    )
    success = result.returncode == 0
    _track_outbound(group_id, message, group_id=group_id, success=success)
    if success:
        return True, "sent to group"
    return False, result.stderr.strip() or "send failed"


def receive(timeout: int = 5, phone: str | None = None, store: bool = False) -> list[dict[str, Any]]:
    acct = phone or default_account()
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


def _track_outbound(
    peer: str,
    body: str,
    group_id: str | None = None,
    success: bool = True,
) -> None:
    ts = int(datetime.now().timestamp() * 1000)
    msg_id = f"sig-out-{ts}-{peer[-4:] if len(peer) >= 4 else peer}"
    try:
        events.record_message(
            channel="signal",
            address=peer,
            direction="out",
            body=body,
            timestamp=ts,
            raw_id=msg_id,
            group_id=group_id,
            success=1 if success else 0,
            sent_by="steward",
        )
    except Exception:
        logger.exception("failed to track outbound signal message to %s", peer)


def _store_messages(phone: str, messages: list[dict[str, Any]]) -> int:
    stored = 0
    for msg in messages:
        try:
            events.record_message(
                channel="signal",
                address=msg["from"],
                direction="in",
                body=msg["body"],
                timestamp=msg["timestamp"],
                raw_id=msg["id"],
                peer_name=msg.get("from_name") or None,
                group_id=msg.get("group"),
                sent_by=msg.get("from_name") or msg["from"],
            )
            stored += 1
        except Exception:
            logger.exception("failed to store signal message %s", msg.get("id"))
    return stored


def get_messages(
    phone: str | None = None,
    sender: str | None = None,
    limit: int = 50,
    unread_only: bool = False,
) -> list[dict[str, Any]]:
    query = "SELECT * FROM messages WHERE channel = 'signal' AND direction = 'in'"
    params: list[Any] = []
    if sender:
        query += " AND peer = ?"
        params.append(sender)
    if unread_only:
        query += " AND read_at IS NULL"
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


def get_conversations(phone: str) -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT peer AS sender_phone, peer_name AS sender_name,
                   COUNT(*) as message_count,
                   MAX(timestamp) as last_timestamp,
                   SUM(CASE WHEN read_at IS NULL THEN 1 ELSE 0 END) as unread_count
            FROM messages
            WHERE channel = 'signal' AND direction = 'in'
            GROUP BY peer
            ORDER BY last_timestamp DESC
            """,
        ).fetchall()
        return [dict(row) for row in rows]


def mark_read(message_id: str) -> bool:
    with get_db() as conn:
        conn.execute(
            "UPDATE messages SET read_at = ? WHERE id = ? AND channel = 'signal'",
            (datetime.now().isoformat(), message_id),
        )
    return True


def get_message(message_id: str) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM messages WHERE channel = 'signal' AND (id = ? OR id LIKE ?)",
            (message_id, f"{message_id}%"),
        ).fetchone()
        return dict(row) if row else None


def reply_to(phone: str, message_id: str, body: str) -> tuple[bool, str, dict[str, Any] | None]:
    msg = get_message(message_id)
    if not msg:
        return False, f"message {message_id} not found", None
    success, result = send_to(phone, msg["peer"], body)
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
    return [{"number": c.get("number", ""), "name": c.get("name", "")} for c in result if c.get("number")]


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
    print(f.getvalue())

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
    phone = default_account()
    if not phone:
        return []
    return list_contacts_for(phone)

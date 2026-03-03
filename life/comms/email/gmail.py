import base64
import hashlib
import json
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, cast

import keyring
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from life.comms.models import Draft

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/gmail.modify",
]
SERVICE_NAME = "comms-cli/gmail"
TOKEN_KEY_SUFFIX = "/token"  # noqa: S105
CREDENTIALS_PATH = Path.home() / ".life/comms/gmail_credentials.json"


def _headers_map(headers: list[dict[str, str]], lower: bool = True) -> dict[str, str]:
    if lower:
        return {h["name"].lower(): h["value"] for h in headers}
    return {h["name"]: h["value"] for h in headers}


def _decode_body(data: str | None) -> str:
    if not data:
        return ""
    try:
        return base64.urlsafe_b64decode(data).decode(errors="replace")
    except Exception:
        return ""


def _extract_body(payload: dict[str, Any]) -> str:
    parts = payload.get("parts") or []
    for part in parts:
        if part.get("mimeType") == "text/plain":
            return _decode_body(part.get("body", {}).get("data"))
        if part.get("mimeType", "").startswith("multipart/"):
            nested = _extract_body(part)
            if nested:
                return nested

    return _decode_body(payload.get("body", {}).get("data"))


def _get_token(email_addr: str) -> dict[str, Any] | None:
    token_json = keyring.get_password(SERVICE_NAME, f"{email_addr}{TOKEN_KEY_SUFFIX}")
    if token_json:
        return json.loads(token_json)
    return None


def _set_token(email_addr: str, token_dict: dict[str, Any]):
    keyring.set_password(SERVICE_NAME, f"{email_addr}{TOKEN_KEY_SUFFIX}", json.dumps(token_dict))


def _get_credentials(email_addr: str | None = None) -> tuple[Credentials, str]:
    if email_addr:
        token_data = _get_token(email_addr)
        creds = None

        if token_data:
            creds = Credentials.from_authorized_user_info(token_data, SCOPES)

        if creds and creds.valid:
            return creds, email_addr

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            _set_token(email_addr, json.loads(creds.to_json()))
            return creds, email_addr

    if not CREDENTIALS_PATH.exists():
        raise ValueError(f"Gmail credentials not found at {CREDENTIALS_PATH}")

    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
    creds = cast(Credentials, flow.run_local_server(port=0))

    service = build("oauth2", "v2", credentials=creds)
    user_info = service.userinfo().get().execute()
    email = user_info.get("email")

    if not email:
        raise ValueError("Failed to get email from OAuth token")

    _set_token(email, json.loads(creds.to_json()))
    return creds, email


def test_connection(account_id: str, email_addr: str) -> tuple[bool, str]:
    try:
        creds, _ = _get_credentials(email_addr)
        service = build("gmail", "v1", credentials=creds)
        service.users().getProfile(userId="me").execute()
        return True, "Connected successfully"
    except Exception as e:
        return False, f"Connection failed: {e}"


def fetch_thread_messages(thread_id: str, email_addr: str) -> list[dict[str, Any]]:
    creds, _ = _get_credentials(email_addr)
    service = build("gmail", "v1", credentials=creds)

    thread = service.users().threads().get(userId="me", id=thread_id, format="full").execute()

    messages = []
    for msg in thread.get("messages", []):
        headers = _headers_map(msg["payload"].get("headers", []))
        body = _extract_body(msg["payload"])

        messages.append(
            {
                "from": headers.get("from", ""),
                "to": headers.get("to", ""),
                "cc": headers.get("cc", ""),
                "date": headers.get("date", ""),
                "subject": headers.get("subject", ""),
                "body": body,
            }
        )

    return messages


def count_inbox_threads(email_addr: str) -> int:
    creds, _ = _get_credentials(email_addr)
    service = build("gmail", "v1", credentials=creds)

    label = service.users().labels().get(userId="me", id="INBOX").execute()
    return label.get("threadsTotal", 0)


def list_threads(
    email_addr: str, label: str = "inbox", max_results: int = 50
) -> list[dict[str, Any]]:
    creds, _ = _get_credentials(email_addr)
    service = build("gmail", "v1", credentials=creds)

    label_queries = {
        "inbox": "in:inbox",
        "unread": "is:unread",
        "archive": "-in:inbox -in:trash -in:spam",
        "trash": "in:trash",
        "starred": "is:starred",
        "sent": "in:sent",
    }

    query = label_queries.get(label, f"in:{label}")

    results = service.users().threads().list(userId="me", q=query, maxResults=max_results).execute()

    threads = []
    for thread_ref in results.get("threads", []):
        thread = (
            service.users()
            .threads()
            .get(
                userId="me",
                id=thread_ref["id"],
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            )
            .execute()
        )

        messages = thread.get("messages", [])
        if not messages:
            continue

        last_msg = messages[-1]
        headers = {h["name"].lower(): h["value"] for h in last_msg["payload"].get("headers", [])}

        threads.append(
            {
                "id": thread_ref["id"],
                "snippet": thread_ref.get("snippet", "(no subject)"),
                "from": headers.get("from", ""),
                "subject": headers.get("subject", ""),
                "date": headers.get("date", ""),
            }
        )

    return threads


def list_inbox_threads(email_addr: str, max_results: int = 50) -> list[dict[str, Any]]:
    return list_threads(email_addr, label="inbox", max_results=max_results)


def fetch_messages(account_id: str, email_addr: str, since_days: int = 7) -> list[dict[str, Any]]:
    creds, _ = _get_credentials(email_addr)
    service = build("gmail", "v1", credentials=creds)

    query = f"newer_than:{since_days}d"
    results = service.users().messages().list(userId="me", q=query, maxResults=100).execute()
    message_ids = results.get("messages", [])

    messages = []
    for msg_ref in message_ids:
        msg = service.users().messages().get(userId="me", id=msg_ref["id"], format="full").execute()

        headers = _headers_map(msg["payload"].get("headers", []))
        msg_id = headers.get("message-id", msg_ref["id"])
        thread_id = msg.get("threadId", msg_id)
        from_addr = headers.get("from", "")
        to_addr = headers.get("to", "")
        subject = headers.get("subject", "")
        date_str = headers.get("date", "")
        body = _extract_body(msg["payload"])

        msg_hash = hashlib.sha256(f"{msg_id}{from_addr}{date_str}".encode()).hexdigest()[:16]
        thread_hash = hashlib.sha256(thread_id.encode()).hexdigest()[:16]

        label_ids = msg.get("labelIds", [])
        status = "unread" if "UNREAD" in label_ids else "read"

        messages.append(
            {
                "id": msg_hash,
                "thread_id": thread_hash,
                "account_id": account_id,
                "provider": "gmail",
                "from_addr": from_addr,
                "to_addr": to_addr,
                "subject": subject,
                "body": body,
                "headers": json.dumps(headers),
                "status": status,
                "date": date_str,
            }
        )

    return messages


def send_message(account_id: str, email_addr: str, draft: Draft) -> bool:
    try:
        creds, _ = _get_credentials(email_addr)
        service = build("gmail", "v1", credentials=creds)

        message = MIMEText(draft.body)
        message["to"] = draft.to_addr
        message["from"] = email_addr
        if draft.cc_addr:
            message["cc"] = draft.cc_addr
        message["subject"] = draft.subject or "(no subject)"

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return True
    except Exception:
        return False


def archive_thread(thread_id: str, email_addr: str) -> bool:
    creds, _ = _get_credentials(email_addr)
    service = build("gmail", "v1", credentials=creds)

    try:
        service.users().threads().modify(
            userId="me", id=thread_id, body={"removeLabelIds": ["INBOX"]}
        ).execute()
        return True
    except Exception:
        return False


def delete_thread(thread_id: str, email_addr: str) -> bool:
    creds, _ = _get_credentials(email_addr)
    service = build("gmail", "v1", credentials=creds)

    try:
        service.users().threads().trash(userId="me", id=thread_id).execute()
        return True
    except Exception:
        return False


def flag_thread(thread_id: str, email_addr: str) -> bool:
    creds, _ = _get_credentials(email_addr)
    service = build("gmail", "v1", credentials=creds)

    try:
        service.users().threads().modify(
            userId="me", id=thread_id, body={"addLabelIds": ["STARRED"]}
        ).execute()
        return True
    except Exception:
        return False


def unflag_thread(thread_id: str, email_addr: str) -> bool:
    creds, _ = _get_credentials(email_addr)
    service = build("gmail", "v1", credentials=creds)

    try:
        service.users().threads().modify(
            userId="me", id=thread_id, body={"removeLabelIds": ["STARRED"]}
        ).execute()
        return True
    except Exception:
        return False


def unarchive_thread(thread_id: str, email_addr: str) -> bool:
    creds, _ = _get_credentials(email_addr)
    service = build("gmail", "v1", credentials=creds)

    try:
        service.users().threads().modify(
            userId="me", id=thread_id, body={"addLabelIds": ["INBOX"]}
        ).execute()
        return True
    except Exception:
        return False


def undelete_thread(thread_id: str, email_addr: str) -> bool:
    creds, _ = _get_credentials(email_addr)
    service = build("gmail", "v1", credentials=creds)

    try:
        service.users().threads().untrash(userId="me", id=thread_id).execute()
        return True
    except Exception:
        return False


def init_oauth() -> str:
    _, email = _get_credentials()
    return email

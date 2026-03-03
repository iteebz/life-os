"""Outlook adapter via Microsoft Graph API."""

import re
from datetime import datetime
from typing import Any

import keyring
import msal
import requests

from life.comms.models import Draft

AUTHORITY = "https://login.microsoftonline.com/common"
SCOPES = ["https://graph.microsoft.com/Mail.ReadWrite", "https://graph.microsoft.com/Mail.Send"]
GRAPH_API = "https://graph.microsoft.com/v1.0"

SERVICE_NAME = "comms-cli/outlook"
TOKEN_KEY_SUFFIX = "/token"  # noqa: S105
CLIENT_ID_SUFFIX = "/client_id"
CLIENT_SECRET_SUFFIX = "/client_secret"  # noqa: S105


def _set_token_cache(email: str, cache_data: str):
    keyring.set_password(SERVICE_NAME, f"{email}{TOKEN_KEY_SUFFIX}", cache_data)


def _get_client_creds(email: str) -> tuple[str | None, str | None]:
    client_id = keyring.get_password(SERVICE_NAME, f"{email}{CLIENT_ID_SUFFIX}")
    client_secret = keyring.get_password(SERVICE_NAME, f"{email}{CLIENT_SECRET_SUFFIX}")
    return client_id, client_secret


def store_credentials(email: str, client_id: str, client_secret: str):
    keyring.set_password(SERVICE_NAME, f"{email}{CLIENT_ID_SUFFIX}", client_id)
    keyring.set_password(SERVICE_NAME, f"{email}{CLIENT_SECRET_SUFFIX}", client_secret)


def _get_access_token(email: str) -> str | None:
    client_id, client_secret = _get_client_creds(email)
    if not client_id or not client_secret:
        return None

    cache = msal.SerializableTokenCache()
    cache_data = keyring.get_password(SERVICE_NAME, f"{email}{TOKEN_KEY_SUFFIX}")
    if cache_data:
        cache.deserialize(cache_data)

    app = msal.ConfidentialClientApplication(
        client_id,
        authority=AUTHORITY,
        client_credential=client_secret,
        token_cache=cache,
    )

    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if result and "access_token" in result:
            if cache.has_state_changed:
                _set_token_cache(email, cache.serialize())
            return str(result["access_token"])

    flow = app.initiate_device_flow(scopes=SCOPES)  # type: ignore[attr-defined]
    if "user_code" not in flow:
        return None

    result = app.acquire_token_by_device_flow(flow)  # type: ignore[attr-defined]

    if "access_token" in result:
        _set_token_cache(email, cache.serialize())
        return str(result["access_token"])

    return None


def _api_get(
    email: str, endpoint: str, params: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    token = _get_access_token(email)
    if not token:
        return None

    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{GRAPH_API}{endpoint}", headers=headers, params=params, timeout=30)
    if resp.status_code == 200:
        return resp.json()
    return None


def _api_post(email: str, endpoint: str, data: dict[str, Any]) -> bool:
    token = _get_access_token(email)
    if not token:
        return False

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = requests.post(f"{GRAPH_API}{endpoint}", headers=headers, json=data, timeout=30)
    return resp.status_code in (200, 201, 202, 204)


def _api_patch(email: str, endpoint: str, data: dict[str, Any]) -> bool:
    token = _get_access_token(email)
    if not token:
        return False

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = requests.patch(f"{GRAPH_API}{endpoint}", headers=headers, json=data, timeout=30)
    return resp.status_code in (200, 204)


def test_connection(
    account_id: str, email: str, client_id: str | None = None, client_secret: str | None = None
) -> tuple[bool, str]:
    if client_id and client_secret:
        store_credentials(email, client_id, client_secret)

    try:
        result = _api_get(email, "/me")
        if result:
            return True, "Connected successfully"
        return False, "Failed to get user profile"
    except Exception as e:
        return False, f"Connection failed: {e}"


def count_inbox_threads(email: str) -> int:
    result = _api_get(email, "/me/mailFolders/inbox")
    if result:
        return result.get("totalItemCount", 0)
    return 0


def list_threads(email: str, label: str = "inbox", max_results: int = 50) -> list[dict[str, Any]]:
    folder_map = {
        "inbox": "inbox",
        "archive": "archive",
        "trash": "deleteditems",
        "sent": "sentitems",
        "drafts": "drafts",
    }
    folder = folder_map.get(label, "inbox")

    params = {
        "$top": max_results,
        "$orderby": "receivedDateTime desc",
        "$select": "id,conversationId,subject,from,receivedDateTime,isRead,bodyPreview",
    }

    if label == "unread":
        params["$filter"] = "isRead eq false"
        folder = "inbox"
    elif label == "starred":
        params["$filter"] = "flag/flagStatus eq 'flagged'"
        folder = "inbox"

    result = _api_get(email, f"/me/mailFolders/{folder}/messages", params)
    if not result:
        return []

    seen_convos = set()
    threads = []

    for msg in result.get("value", []):
        convo_id = msg.get("conversationId", msg["id"])
        if convo_id in seen_convos:
            continue
        seen_convos.add(convo_id)

        from_data = msg.get("from", {}).get("emailAddress", {})
        from_addr = from_data.get("address", "")
        from_name = from_data.get("name", from_addr)

        received = msg.get("receivedDateTime", "")
        timestamp = 0
        if received:
            try:
                dt = datetime.fromisoformat(received)
                timestamp = int(dt.timestamp() * 1000)
            except ValueError:
                pass

        threads.append(
            {
                "id": convo_id,
                "message_id": msg["id"],
                "snippet": msg.get("bodyPreview", "")[:100],
                "from": from_name,
                "subject": msg.get("subject", "(no subject)"),
                "date": received[:16] if received else "",
                "timestamp": timestamp,
                "labels": [] if msg.get("isRead", True) else ["UNREAD"],
            }
        )

    return threads


def _format_recipients(recipients: list[dict[str, Any]]) -> str:
    parts = []
    for r in recipients:
        addr = r.get("emailAddress", {})
        email_addr = addr.get("address", "")
        name = addr.get("name", "")
        if name and name != email_addr:
            parts.append(f"{name} <{email_addr}>")
        else:
            parts.append(email_addr)
    return ", ".join(parts)


def fetch_thread_messages(thread_id: str, email: str) -> list[dict[str, Any]]:
    params = {
        "$filter": f"conversationId eq '{thread_id}'",
        "$orderby": "receivedDateTime asc",
        "$select": "id,subject,from,toRecipients,ccRecipients,receivedDateTime,body",
        "$top": 50,
    }

    result = _api_get(email, "/me/messages", params)
    if not result:
        return []

    messages = []
    for msg in result.get("value", []):
        from_data = msg.get("from", {}).get("emailAddress", {})
        from_addr = from_data.get("address", "")
        from_name = from_data.get("name", from_addr)

        body_content = msg.get("body", {}).get("content", "")
        if msg.get("body", {}).get("contentType") == "html":
            body_content = re.sub(r"<[^>]+>", "", body_content)
            body_content = body_content.strip()

        messages.append(
            {
                "from": f"{from_name} <{from_addr}>" if from_name != from_addr else from_addr,
                "to": _format_recipients(msg.get("toRecipients", [])),
                "cc": _format_recipients(msg.get("ccRecipients", [])),
                "date": msg.get("receivedDateTime", ""),
                "subject": msg.get("subject", ""),
                "body": body_content,
            }
        )

    return messages


def archive_thread(thread_id: str, email: str) -> bool:
    params = {"$filter": f"conversationId eq '{thread_id}'", "$select": "id"}
    result = _api_get(email, "/me/mailFolders/inbox/messages", params)
    if not result:
        return False

    archive_id = _get_or_create_archive_folder(email)
    if not archive_id:
        return False

    success = True
    for msg in result.get("value", []):
        if not _api_post(email, f"/me/messages/{msg['id']}/move", {"destinationId": archive_id}):
            success = False

    return success


def _get_or_create_archive_folder(email: str) -> str | None:
    result = _api_get(email, "/me/mailFolders", {"$filter": "displayName eq 'Archive'"})
    if result and result.get("value"):
        return result["value"][0]["id"]

    resp = _api_post(email, "/me/mailFolders", {"displayName": "Archive"})
    if resp:
        result = _api_get(email, "/me/mailFolders", {"$filter": "displayName eq 'Archive'"})
        if result and result.get("value"):
            return result["value"][0]["id"]

    return None


def delete_thread(thread_id: str, email: str) -> bool:
    params = {"$filter": f"conversationId eq '{thread_id}'", "$select": "id"}
    result = _api_get(email, "/me/messages", params)
    if not result:
        return False

    success = True
    for msg in result.get("value", []):
        if not _api_post(
            email, f"/me/messages/{msg['id']}/move", {"destinationId": "deleteditems"}
        ):
            success = False

    return success


def flag_thread(thread_id: str, email: str) -> bool:
    return _set_thread_flag(thread_id, email, "flagged")


def unflag_thread(thread_id: str, email: str) -> bool:
    return _set_thread_flag(thread_id, email, "notFlagged")


def _set_thread_flag(thread_id: str, email: str, flag_status: str) -> bool:
    params = {"$filter": f"conversationId eq '{thread_id}'", "$select": "id"}
    result = _api_get(email, "/me/messages", params)
    if not result:
        return False

    success = True
    for msg in result.get("value", []):
        if not _api_patch(
            email, f"/me/messages/{msg['id']}", {"flag": {"flagStatus": flag_status}}
        ):
            success = False

    return success


def unarchive_thread(thread_id: str, email: str) -> bool:
    archive_id = _get_or_create_archive_folder(email)
    if not archive_id:
        return False

    params = {"$filter": f"conversationId eq '{thread_id}'", "$select": "id"}
    result = _api_get(email, f"/me/mailFolders/{archive_id}/messages", params)
    if not result:
        return False

    inbox_result = _api_get(email, "/me/mailFolders/inbox")
    if not inbox_result:
        return False
    inbox_id = inbox_result["id"]

    success = True
    for msg in result.get("value", []):
        if not _api_post(email, f"/me/messages/{msg['id']}/move", {"destinationId": inbox_id}):
            success = False

    return success


def undelete_thread(thread_id: str, email: str) -> bool:
    params = {"$filter": f"conversationId eq '{thread_id}'", "$select": "id"}
    result = _api_get(email, "/me/mailFolders/deleteditems/messages", params)
    if not result:
        return False

    inbox_result = _api_get(email, "/me/mailFolders/inbox")
    if not inbox_result:
        return False
    inbox_id = inbox_result["id"]

    success = True
    for msg in result.get("value", []):
        if not _api_post(email, f"/me/messages/{msg['id']}/move", {"destinationId": inbox_id}):
            success = False

    return success


def send_message(account_id: str, email: str, draft: Draft) -> bool:
    message = {
        "message": {
            "subject": draft.subject or "(no subject)",
            "body": {"contentType": "Text", "content": draft.body},
            "toRecipients": [{"emailAddress": {"address": draft.to_addr}}],
        }
    }

    if draft.cc_addr:
        message["message"]["ccRecipients"] = [{"emailAddress": {"address": draft.cc_addr}}]

    return _api_post(email, "/me/sendMail", message)

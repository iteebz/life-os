import os

import httpx
import keyring

SERVICE_NAME = "comms-cli/resend"


def _get_api_key() -> str | None:
    return os.environ.get("RESEND_API_KEY") or keyring.get_password(SERVICE_NAME, "api_key")


def store_api_key(api_key: str):
    keyring.set_password(SERVICE_NAME, "api_key", api_key)


def is_configured() -> bool:
    return _get_api_key() is not None


def test_connection() -> tuple[bool, str]:
    api_key = _get_api_key()
    if not api_key:
        return False, "No API key configured"

    try:
        resp = httpx.get(
            "https://api.resend.com/domains",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        if resp.status_code == 200:
            domains = resp.json().get("data", [])
            verified = [d["name"] for d in domains if d.get("status") == "verified"]
            if verified:
                return True, f"Connected. Verified domains: {', '.join(verified)}"
            return True, "Connected. No verified domains yet."
        return False, f"API error: {resp.status_code}"
    except Exception as e:
        return False, f"Connection failed: {e}"


def send_message(from_addr: str, to_addr: str, subject: str, body: str) -> tuple[bool, str]:
    api_key = _get_api_key()
    if not api_key:
        return False, "No API key configured"

    try:
        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "from": from_addr,
                "to": [to_addr],
                "subject": subject,
                "text": body,
            },
        )
        if resp.status_code == 200:
            return True, resp.json().get("id", "sent")
        return False, f"API error: {resp.status_code} - {resp.text}"
    except Exception as e:
        return False, f"Send failed: {e}"


def send_draft(from_addr: str, draft) -> tuple[bool, str]:
    return send_message(
        from_addr=from_addr,
        to_addr=draft.to_addr,
        subject=draft.subject or "(no subject)",
        body=draft.body,
    )

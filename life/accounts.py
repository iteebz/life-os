"""life accounts — link/unlink/list email and signal accounts."""

from __future__ import annotations

from fncli import cli

from .lib.errors import exit_error


@cli("life accounts", name="ls")
def accounts_list():
    """List all linked accounts"""
    from .comms import accounts as accts_module

    accts = accts_module.list_accounts()
    if not accts:
        print("no accounts linked")
        print("  link email:  life accounts link gmail")
        print("  link signal: life accounts link signal")
        return
    for a in accts:
        status = "✓" if a["enabled"] else "✗"
        print(f"  {status} {a['provider']:10} {a['email']}")


@cli("life accounts", name="link")
def link(provider: str, client_id: str | None = None, client_secret: str | None = None):
    """Link an account: gmail, outlook, signal"""
    from .comms import accounts as accts_module

    if provider == "gmail":
        from .comms.adapters.email import gmail

        try:
            email_addr = gmail.init_oauth()
            print(f"oauth completed: {email_addr}")
        except Exception as e:
            exit_error(f"oauth failed: {e}")
        account_id = accts_module.add_email_account(provider, email_addr)
        ok, err = gmail.test_connection(account_id, email_addr)
        if not ok:
            exit_error(f"connection failed: {err}")
        print(f"linked gmail: {email_addr}")

    elif provider == "outlook":
        from .comms.adapters.email import outlook

        if not client_id or not client_secret:
            exit_error("outlook requires --client-id and --client-secret")
        account_id = accts_module.add_email_account(provider, "")
        outlook.store_credentials("", client_id, client_secret)
        ok, err = outlook.test_connection(account_id, "", client_id, client_secret)
        if not ok:
            exit_error(f"connection failed: {err}")
        print("linked outlook")

    elif provider == "signal":
        from . import signal as signal_module

        print("linking Signal as secondary device...")
        print("open Signal → Settings → Linked Devices → Link New Device, then scan the QR code")
        ok, err = signal_module.link_device("life-cli")
        if not ok:
            exit_error(f"link failed: {err}")
        accounts = signal_module.list_accounts()
        if not accounts:
            exit_error("no accounts found after linking")
        phone = accounts[0]
        accts_module.add_messaging_account("signal", phone)
        print(f"linked signal: {phone}")

    else:
        exit_error(f"unknown provider: {provider}. use: gmail, outlook, signal")


@cli("life accounts", name="unlink")
def unlink(account_id: str):
    """Unlink an account by ID or email"""
    from .comms import accounts as accts_module

    accts = accts_module.list_accounts()
    matching = [a for a in accts if a["id"].startswith(account_id) or a["email"] == account_id]
    if not matching:
        exit_error(f"no account matching: {account_id}")
    if len(matching) > 1:
        for a in matching:
            print(f"  {a['id'][:8]} {a['provider']} {a['email']}")
        exit_error("ambiguous — be more specific")
    acct = matching[0]
    if accts_module.remove_account(acct["id"]):
        print(f"unlinked {acct['provider']}: {acct['email']}")
    else:
        exit_error("failed to unlink")

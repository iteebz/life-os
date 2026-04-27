"""Telegram sync and auth. Read messages via `life messages`.

life tg sync <person>             incremental sync from telegram
life tg sync <person> --full      full re-sync
life tg auth <api_id> <hash>      one-time user API setup
"""

from fncli import cli

from life.comms.messages import telegram as _tg


@cli("life tg sync", default=True, flags={"full": ["--full"]})
def tg_sync_cmd(person: str, full: bool = False):
    """Sync telegram chat history from the cloud"""
    from life.comms.messages.telegram_sync import sync

    chat_id = _tg.resolve_chat_id(person)
    if chat_id is None:
        chat_ref: str | int = person
    else:
        chat_ref = chat_id

    n = sync(chat_ref, full=full)
    print(f"synced {n} messages from {person}")


@cli("life tg", name="auth")
def tg_auth_cmd(api_id: int, api_hash: str):
    """Store Telegram user API credentials (from my.telegram.org)"""
    from life.comms.messages.telegram_sync import save_credentials

    save_credentials(api_id, api_hash)
    print(f"saved — api_id={api_id}. run: life tg sync <person> to pull history")

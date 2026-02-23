CREATE TABLE IF NOT EXISTS telegram_messages (
    id          INTEGER PRIMARY KEY,
    chat_id     INTEGER NOT NULL,
    from_id     INTEGER,
    from_name   TEXT,
    body        TEXT NOT NULL,
    timestamp   INTEGER NOT NULL,
    direction   TEXT NOT NULL DEFAULT 'in',
    read_at     TEXT,
    received_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_telegram_messages_chat ON telegram_messages(chat_id);
CREATE INDEX IF NOT EXISTS idx_telegram_messages_ts ON telegram_messages(timestamp);

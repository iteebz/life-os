CREATE TABLE IF NOT EXISTS messages (
    id          TEXT PRIMARY KEY,
    channel     TEXT NOT NULL,
    direction   TEXT NOT NULL,
    peer        TEXT NOT NULL,
    peer_name   TEXT,
    body        TEXT NOT NULL,
    subject     TEXT,
    sent_by     TEXT DEFAULT 'steward',
    draft_id    TEXT,
    group_id    TEXT,
    success     INTEGER,
    error       TEXT,
    read_at     TEXT,
    timestamp   INTEGER NOT NULL,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_messages_channel ON messages(channel);
CREATE INDEX IF NOT EXISTS idx_messages_peer ON messages(peer);
CREATE INDEX IF NOT EXISTS idx_messages_direction ON messages(direction);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_messages_channel_peer_ts ON messages(channel, peer, timestamp DESC);

INSERT OR IGNORE INTO messages (id, channel, direction, peer, peer_name, body, group_id, read_at, timestamp, created_at)
SELECT
    id,
    'signal',
    'in',
    sender_phone,
    sender_name,
    body,
    group_id,
    read_at,
    timestamp,
    received_at
FROM signal_messages;

INSERT OR IGNORE INTO messages (id, channel, direction, peer, peer_name, body, timestamp)
SELECT
    'tg-' || CAST(id AS TEXT),
    'telegram',
    direction,
    CAST(chat_id AS TEXT),
    from_name,
    body,
    timestamp
FROM telegram_messages;

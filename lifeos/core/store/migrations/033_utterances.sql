CREATE TABLE IF NOT EXISTS utterances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER UNIQUE REFERENCES events(id),
    session_id INTEGER REFERENCES sessions(id),
    body TEXT NOT NULL,
    ts INTEGER NOT NULL,
    source TEXT NOT NULL DEFAULT 'human',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_utterances_ts ON utterances(ts DESC);
CREATE INDEX IF NOT EXISTS idx_utterances_session ON utterances(session_id);

CREATE VIRTUAL TABLE IF NOT EXISTS utterances_fts USING fts5(
    body,
    content=utterances,
    content_rowid=id
);

CREATE TRIGGER IF NOT EXISTS utterances_ai AFTER INSERT ON utterances BEGIN
    INSERT INTO utterances_fts(rowid, body) VALUES (new.id, new.body);
END;

CREATE TRIGGER IF NOT EXISTS utterances_ad AFTER DELETE ON utterances BEGIN
    INSERT INTO utterances_fts(utterances_fts, rowid, body) VALUES ('delete', old.id, old.body);
END;

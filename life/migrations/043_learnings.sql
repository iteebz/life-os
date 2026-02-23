CREATE TABLE IF NOT EXISTS learnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    body TEXT NOT NULL,
    tags TEXT,
    logged_at TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%S', 'now')),
    CHECK (length(body) > 0)
);

CREATE INDEX IF NOT EXISTS idx_learnings_at ON learnings(logged_at);

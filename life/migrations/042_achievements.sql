CREATE TABLE IF NOT EXISTS achievements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    tags TEXT,
    achieved_at TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%S', 'now')),
    CHECK (length(name) > 0)
);

CREATE INDEX IF NOT EXISTS idx_achievements_at ON achievements(achieved_at);

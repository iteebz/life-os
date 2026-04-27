CREATE TABLE IF NOT EXISTS spawns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mode TEXT NOT NULL,
    source TEXT,
    session_id INTEGER REFERENCES sessions(id),
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,
    runtime_seconds INTEGER,
    prompt_chars INTEGER,
    response_chars INTEGER,
    status TEXT NOT NULL DEFAULT 'active'
);

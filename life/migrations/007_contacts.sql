CREATE TABLE contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    cadence_days INTEGER NOT NULL DEFAULT 30,
    last_contact_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

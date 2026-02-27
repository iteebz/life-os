PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    focus BOOLEAN DEFAULT 0,
    scheduled_date TEXT,
    created TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%S', 'now')),
    completed_at TEXT,
    parent_id TEXT REFERENCES tasks(id) ON DELETE CASCADE,
    scheduled_time TEXT CHECK (scheduled_time IS NULL OR TIME(scheduled_time) IS NOT NULL),
    blocked_by TEXT REFERENCES tasks(id) ON DELETE SET NULL,
    description TEXT,
    steward BOOLEAN NOT NULL DEFAULT 0,
    source TEXT CHECK (source IS NULL OR source IN ('tyson', 'steward', 'scheduled')),
    is_deadline INTEGER NOT NULL DEFAULT 0,
    CHECK (length(content) > 0),
    CHECK (scheduled_date IS NULL OR DATE(scheduled_date) IS NOT NULL)
);

CREATE TABLE habits (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    created TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%S', 'now')),
    archived_at TIMESTAMP NULL,
    parent_id TEXT REFERENCES habits(id) ON DELETE CASCADE,
    private BOOLEAN NOT NULL DEFAULT 0,
    CHECK (length(content) > 0)
);

CREATE TABLE habit_checks (
    habit_id TEXT NOT NULL,
    check_date TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    PRIMARY KEY (habit_id, check_date),
    FOREIGN KEY (habit_id) REFERENCES habits(id) ON DELETE CASCADE,
    CHECK (DATE(check_date) IS NOT NULL),
    CHECK (DATETIME(completed_at) IS NOT NULL)
);

CREATE TABLE tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT,
    habit_id TEXT,
    tag TEXT NOT NULL,
    CHECK (length(tag) > 0),
    CHECK ((task_id IS NOT NULL AND habit_id IS NULL) OR (task_id IS NULL AND habit_id IS NOT NULL)),
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    FOREIGN KEY (habit_id) REFERENCES habits(id) ON DELETE CASCADE,
    UNIQUE(task_id, habit_id, tag)
);

CREATE TABLE task_mutations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    field TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    mutated_at TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%S', 'now')),
    reason TEXT
);

CREATE TABLE deleted_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    content TEXT NOT NULL,
    tags TEXT,
    deleted_at TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%S', 'now')),
    cancel_reason TEXT,
    cancelled INTEGER NOT NULL DEFAULT 0
);


CREATE TABLE patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    body TEXT NOT NULL,
    logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    tag TEXT
);

CREATE TABLE steward_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    summary TEXT NOT NULL,
    logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    body TEXT NOT NULL,
    logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    tag TEXT,
    about_date DATE
);

CREATE TABLE mood_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    score INTEGER NOT NULL CHECK (score BETWEEN 1 AND 5),
    label TEXT,
    logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE special_dates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    month INTEGER NOT NULL,
    day INTEGER NOT NULL,
    type TEXT NOT NULL DEFAULT 'other',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE improvements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    body TEXT NOT NULL,
    logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    done_at TIMESTAMP
);

CREATE TABLE achievements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    tags TEXT,
    achieved_at TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%S', 'now')),
    CHECK (length(name) > 0)
);


CREATE TABLE accounts (
    id TEXT PRIMARY KEY,
    service_type TEXT NOT NULL,
    provider TEXT NOT NULL,
    email TEXT NOT NULL,
    auth_data TEXT,
    enabled INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(provider, email)
);

CREATE TABLE drafts (
    id TEXT PRIMARY KEY,
    thread_id TEXT,
    to_addr TEXT NOT NULL,
    cc_addr TEXT,
    subject TEXT,
    body TEXT NOT NULL,
    claude_reasoning TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approved_at TIMESTAMP,
    sent_at TIMESTAMP,
    from_account_id TEXT,
    from_addr TEXT
);

CREATE TABLE sender_stats (
    id TEXT PRIMARY KEY,
    sender TEXT NOT NULL UNIQUE,
    received_count INTEGER DEFAULT 0,
    replied_count INTEGER DEFAULT 0,
    archived_count INTEGER DEFAULT 0,
    deleted_count INTEGER DEFAULT 0,
    flagged_count INTEGER DEFAULT 0,
    avg_response_hours REAL,
    last_received_at TEXT,
    last_action_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE messages (
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


CREATE INDEX idx_tasks_due ON tasks(scheduled_date) WHERE scheduled_date IS NOT NULL;
CREATE INDEX idx_tasks_completed_at ON tasks(completed_at) WHERE completed_at IS NOT NULL;
CREATE INDEX idx_tasks_focus ON tasks(focus) WHERE focus = 1;
CREATE INDEX idx_tasks_parent ON tasks(parent_id) WHERE parent_id IS NOT NULL;
CREATE INDEX idx_tasks_blocked_by ON tasks(blocked_by) WHERE blocked_by IS NOT NULL;
CREATE INDEX idx_habits_created ON habits(created);
CREATE INDEX idx_habits_parent ON habits(parent_id) WHERE parent_id IS NOT NULL;
CREATE INDEX idx_checks_date ON habit_checks(check_date);
CREATE INDEX idx_tags_task ON tags(task_id);
CREATE INDEX idx_tags_habit ON tags(habit_id);
CREATE INDEX idx_tags_name ON tags(tag);
CREATE UNIQUE INDEX idx_tags_task_unique ON tags(task_id, tag) WHERE task_id IS NOT NULL;
CREATE UNIQUE INDEX idx_tags_habit_unique ON tags(habit_id, tag) WHERE habit_id IS NOT NULL;
CREATE INDEX idx_mutations_task ON task_mutations(task_id);
CREATE INDEX idx_mutations_field ON task_mutations(field);
CREATE INDEX idx_mutations_at ON task_mutations(mutated_at);
CREATE INDEX idx_deleted_tasks_at ON deleted_tasks(deleted_at);
CREATE INDEX idx_observations_tag ON observations(tag) WHERE tag IS NOT NULL;
CREATE INDEX idx_achievements_at ON achievements(achieved_at);
CREATE INDEX idx_drafts_approved ON drafts(approved_at);
CREATE INDEX idx_messages_channel ON messages(channel);
CREATE INDEX idx_messages_peer ON messages(peer);
CREATE INDEX idx_messages_direction ON messages(direction);
CREATE INDEX idx_messages_timestamp ON messages(timestamp DESC);
CREATE INDEX idx_messages_channel_peer_ts ON messages(channel, peer, timestamp DESC);

CREATE VIRTUAL TABLE tasks_fts USING fts5(
    content,
    content='tasks',
    content_rowid='rowid',
    tokenize='porter unicode61'
);

CREATE TRIGGER tasks_fts_insert AFTER INSERT ON tasks BEGIN
    INSERT INTO tasks_fts(rowid, content) VALUES (NEW.rowid, NEW.content);
END;
CREATE TRIGGER tasks_fts_update AFTER UPDATE ON tasks BEGIN
    UPDATE tasks_fts SET content = NEW.content WHERE rowid = OLD.rowid;
END;
CREATE TRIGGER tasks_fts_delete AFTER DELETE ON tasks BEGIN
    DELETE FROM tasks_fts WHERE rowid = OLD.rowid;
END;

CREATE VIRTUAL TABLE habits_fts USING fts5(
    content,
    content='habits',
    content_rowid='rowid',
    tokenize='porter unicode61'
);

CREATE TRIGGER habits_fts_insert AFTER INSERT ON habits BEGIN
    INSERT INTO habits_fts(rowid, content) VALUES (NEW.rowid, NEW.content);
END;
CREATE TRIGGER habits_fts_update AFTER UPDATE ON habits BEGIN
    UPDATE habits_fts SET content = NEW.content WHERE rowid = OLD.rowid;
END;
CREATE TRIGGER habits_fts_delete AFTER DELETE ON habits BEGIN
    DELETE FROM habits_fts WHERE rowid = OLD.rowid;
END;

CREATE VIRTUAL TABLE tags_fts USING fts5(
    tag,
    content='tags',
    content_rowid='rowid',
    tokenize='porter unicode61'
);

CREATE TRIGGER tags_fts_insert AFTER INSERT ON tags BEGIN
    INSERT INTO tags_fts(rowid, tag) VALUES (NEW.rowid, NEW.tag);
END;
CREATE TRIGGER tags_fts_update AFTER UPDATE ON tags BEGIN
    UPDATE tags_fts SET tag = NEW.tag WHERE rowid = OLD.rowid;
END;
CREATE TRIGGER tags_fts_delete AFTER DELETE ON tags BEGIN
    DELETE FROM tags_fts WHERE rowid = OLD.rowid;
END;

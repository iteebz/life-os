-- Promote uuid column to id (TEXT PRIMARY KEY) for observations, improvements, achievements.
-- Completes the half-finished 003/004 migrations that added uuid columns but left integer id in place.

CREATE TABLE observations_new (
    id TEXT PRIMARY KEY,
    body TEXT NOT NULL,
    logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    tag TEXT,
    about_date DATE,
    deleted_at TIMESTAMP
);
INSERT INTO observations_new (id, body, logged_at, tag, about_date, deleted_at)
    SELECT uuid, body, logged_at, tag, about_date, deleted_at FROM observations;
DROP TABLE observations;
ALTER TABLE observations_new RENAME TO observations;
CREATE INDEX idx_observations_tag ON observations(tag) WHERE tag IS NOT NULL;

CREATE TABLE improvements_new (
    id TEXT PRIMARY KEY,
    body TEXT NOT NULL,
    logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    done_at TIMESTAMP,
    deleted_at TIMESTAMP
);
INSERT INTO improvements_new (id, body, logged_at, done_at, deleted_at)
    SELECT uuid, body, logged_at, done_at, deleted_at FROM improvements;
DROP TABLE improvements;
ALTER TABLE improvements_new RENAME TO improvements;

CREATE TABLE achievements_new (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    tags TEXT,
    achieved_at TEXT NOT NULL DEFAULT (STRFTIME('%Y-%m-%dT%H:%M:%S', 'now')),
    CHECK (length(name) > 0)
);
INSERT INTO achievements_new (id, name, description, tags, achieved_at)
    SELECT uuid, name, description, tags, achieved_at FROM achievements;
DROP TABLE achievements;
ALTER TABLE achievements_new RENAME TO achievements;
CREATE INDEX idx_achievements_at ON achievements(achieved_at);

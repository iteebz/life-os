-- Unify spawns into sessions. One table, one primitive.
-- Absorb live-tracking columns from spawns, drop mode.

ALTER TABLE sessions ADD COLUMN state TEXT NOT NULL DEFAULT 'closed';
ALTER TABLE sessions ADD COLUMN started_at TIMESTAMP;
ALTER TABLE sessions ADD COLUMN last_active_at TIMESTAMP;
ALTER TABLE sessions ADD COLUMN ended_at TIMESTAMP;
ALTER TABLE sessions ADD COLUMN pid INTEGER;
ALTER TABLE sessions ADD COLUMN runtime_seconds INTEGER;
ALTER TABLE sessions ADD COLUMN prompt_chars INTEGER;
ALTER TABLE sessions ADD COLUMN response_chars INTEGER;

-- Backfill from spawns: most recent spawn per session wins
UPDATE sessions SET
    state = 'closed',
    started_at = COALESCE(
        (SELECT sp.started_at FROM spawns sp WHERE sp.session_id = sessions.id ORDER BY sp.started_at DESC LIMIT 1),
        sessions.logged_at
    ),
    last_active_at = (SELECT sp.last_active_at FROM spawns sp WHERE sp.session_id = sessions.id ORDER BY sp.started_at DESC LIMIT 1),
    ended_at = (SELECT sp.ended_at FROM spawns sp WHERE sp.session_id = sessions.id ORDER BY sp.started_at DESC LIMIT 1),
    pid = NULL,
    runtime_seconds = (SELECT sp.runtime_seconds FROM spawns sp WHERE sp.session_id = sessions.id ORDER BY sp.started_at DESC LIMIT 1),
    prompt_chars = (SELECT sp.prompt_chars FROM spawns sp WHERE sp.session_id = sessions.id ORDER BY sp.started_at DESC LIMIT 1),
    response_chars = (SELECT sp.response_chars FROM spawns sp WHERE sp.session_id = sessions.id ORDER BY sp.started_at DESC LIMIT 1);

-- Backfill sessions that had no matching spawn
UPDATE sessions SET started_at = logged_at WHERE started_at IS NULL;

-- Update events FK: spawn_id → session_id (repoint to the session the spawn belonged to)
UPDATE events SET spawn_id = (
    SELECT sp.session_id FROM spawns sp WHERE sp.id = events.spawn_id
) WHERE spawn_id IS NOT NULL;

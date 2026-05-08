-- Rename events.spawn_id → events.session_id (spawns table absorbed in 022, dropped in 027)
-- Rename sessions.claude_session_id → sessions.provider_session_id (cleaner naming)
ALTER TABLE events RENAME COLUMN spawn_id TO session_id;
ALTER TABLE sessions RENAME COLUMN claude_session_id TO provider_session_id;

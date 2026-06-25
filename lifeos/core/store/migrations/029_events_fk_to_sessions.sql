-- Rebuild events: drop stale FK to spawns(id), point at sessions(id).
-- spawns was dropped in 027 but events.session_id still referenced it,
-- causing every INSERT to fail under PRAGMA foreign_keys=ON. Silent failure
-- via contextlib.suppress in hook._log_turn — ctx meter always read 0%.
-- The messages view depends on events, so drop + recreate around the rename.

DROP VIEW IF EXISTS messages;

CREATE TABLE events_new (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL,
  kind TEXT NOT NULL,
  peer_id INTEGER REFERENCES peers(id),
  channel TEXT,
  ref_id INTEGER REFERENCES events(id),
  session_id INTEGER REFERENCES sessions(id),
  payload TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO events_new (id, ts, kind, peer_id, channel, ref_id, session_id, payload, created_at)
SELECT id, ts, kind, peer_id, channel, ref_id, session_id, payload, created_at FROM events;

DROP TABLE events;
ALTER TABLE events_new RENAME TO events;

CREATE INDEX idx_events_ts ON events(ts DESC);
CREATE INDEX idx_events_peer_ts ON events(peer_id, ts DESC);
CREATE INDEX idx_events_kind_ts ON events(kind, ts DESC);
CREATE INDEX idx_events_ref ON events(ref_id);

CREATE VIEW messages AS
SELECT
  json_extract(e.payload, '$.raw_id') AS id,
  e.channel AS channel,
  CASE e.kind WHEN 'inbound' THEN 'in' WHEN 'outbound' THEN 'out' ELSE e.kind END AS direction,
  pa.address AS peer,
  p.display_name AS peer_name,
  json_extract(e.payload, '$.body') AS body,
  json_extract(e.payload, '$.subject') AS subject,
  COALESCE(json_extract(e.payload, '$.sent_by'), 'steward') AS sent_by,
  NULL AS draft_id,
  json_extract(e.payload, '$.group_id') AS group_id,
  json_extract(e.payload, '$.success') AS success,
  json_extract(e.payload, '$.error') AS error,
  json_extract(e.payload, '$.read_at') AS read_at,
  e.ts AS timestamp,
  e.created_at AS created_at,
  json_extract(e.payload, '$.image_path') AS image_path
FROM events e
LEFT JOIN peers p ON p.id = e.peer_id
LEFT JOIN peer_addresses pa ON pa.peer_id = e.peer_id AND pa.channel = e.channel
WHERE e.kind IN ('inbound', 'outbound');

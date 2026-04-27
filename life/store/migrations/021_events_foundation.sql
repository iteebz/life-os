-- Phase 1: events-as-truth foundation. Additive only.
-- Creates peers, peer_addresses, events. Backfills from messages.
-- Renames messages → messages_legacy. Creates messages view for read compatibility.
-- No code changes required — old reads work via the view.

CREATE TABLE peers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  display_name TEXT NOT NULL,
  contact_id INTEGER,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE peer_addresses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  peer_id INTEGER NOT NULL REFERENCES peers(id),
  channel TEXT NOT NULL,
  address TEXT NOT NULL,
  UNIQUE(channel, address)
);
CREATE INDEX idx_peer_addr_peer ON peer_addresses(peer_id);

CREATE TABLE events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL,
  kind TEXT NOT NULL,
  peer_id INTEGER REFERENCES peers(id),
  channel TEXT,
  ref_id INTEGER REFERENCES events(id),
  spawn_id INTEGER REFERENCES spawns(id),
  payload TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_events_ts ON events(ts DESC);
CREATE INDEX idx_events_peer_ts ON events(peer_id, ts DESC);
CREATE INDEX idx_events_kind_ts ON events(kind, ts DESC);
CREATE INDEX idx_events_ref ON events(ref_id);

-- Stage one peer per (channel, address) with deterministic ids by first-seen order.
CREATE TEMP TABLE _peer_seed AS
SELECT
  ROW_NUMBER() OVER (ORDER BY MIN(timestamp), channel, peer) AS pid,
  channel,
  peer AS address,
  COALESCE(
    (SELECT m2.peer_name FROM messages m2
     WHERE m2.channel = m.channel AND m2.peer = m.peer AND m2.peer_name IS NOT NULL
     ORDER BY m2.timestamp DESC LIMIT 1),
    peer
  ) AS display_name,
  MIN(created_at) AS first_seen
FROM messages m
GROUP BY channel, peer;

INSERT INTO peers (id, display_name, created_at)
SELECT pid, display_name, first_seen FROM _peer_seed;

INSERT INTO peer_addresses (peer_id, channel, address)
SELECT pid, channel, address FROM _peer_seed;

-- Backfill events from messages. Map direction in/out → inbound/outbound.
INSERT INTO events (ts, kind, peer_id, channel, payload, created_at)
SELECT
  m.timestamp,
  CASE m.direction WHEN 'in' THEN 'inbound' WHEN 'out' THEN 'outbound' ELSE m.direction END,
  ps.pid,
  m.channel,
  json_object(
    'body', m.body,
    'subject', m.subject,
    'image_path', m.image_path,
    'success', m.success,
    'error', m.error,
    'sent_by', m.sent_by,
    'raw_id', m.id,
    'group_id', m.group_id,
    'read_at', m.read_at
  ),
  m.created_at
FROM messages m
JOIN _peer_seed ps ON ps.channel = m.channel AND ps.address = m.peer
ORDER BY m.timestamp, m.id;

DROP TABLE _peer_seed;

-- Rename messages → messages_legacy, replace with a view.
ALTER TABLE messages RENAME TO messages_legacy;

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

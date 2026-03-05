ALTER TABLE habits ADD COLUMN cadence TEXT NOT NULL DEFAULT 'daily'
  CHECK (cadence IN ('daily', 'weekly'));

-- Add UUID reference column to achievements, backfill existing rows.
ALTER TABLE achievements ADD COLUMN uuid TEXT;
UPDATE achievements SET uuid = lower(hex(randomblob(4))) WHERE uuid IS NULL;

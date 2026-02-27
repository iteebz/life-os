-- Add UUID columns to observations and improvements.
-- Backfill existing rows with random UUIDs.
ALTER TABLE observations ADD COLUMN uuid TEXT;
ALTER TABLE improvements ADD COLUMN uuid TEXT;
UPDATE observations SET uuid = lower(hex(randomblob(16))) WHERE uuid IS NULL;
UPDATE improvements SET uuid = lower(hex(randomblob(16))) WHERE uuid IS NULL;

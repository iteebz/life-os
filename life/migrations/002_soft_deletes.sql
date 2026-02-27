-- Soft delete support: observations and improvements get deleted_at.
-- Hard deletes are prohibited — data is recoverable.
ALTER TABLE observations ADD COLUMN deleted_at TIMESTAMP;
ALTER TABLE improvements ADD COLUMN deleted_at TIMESTAMP;

-- Rename description → notes on tasks. Drop deleted_tasks — soft deletes via tasks.deleted_at.
ALTER TABLE tasks RENAME COLUMN description TO notes;
DELETE FROM deleted_tasks;
DROP TABLE deleted_tasks;

-- Rename multi-word tables to single-word equivalents
ALTER TABLE steward_sessions RENAME TO sessions;
ALTER TABLE mood_log RENAME TO moods;
ALTER TABLE task_mutations RENAME TO mutations;

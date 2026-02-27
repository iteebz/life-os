-- Collapse patterns table into observations. patterns and observations were
-- conceptually identical; observations is now the single store for all
-- steward context (ephemeral via about_date, permanent otherwise).
DROP TABLE IF EXISTS patterns;

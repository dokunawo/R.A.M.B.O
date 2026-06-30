-- Add the PrizePicks projection tier (standard | demon | goblin) to prop_lines.
-- Tiers share a player/stat but always carry distinct lines (goblin < standard <
-- demon), so the existing STORED snapshot_key (which includes `line`) cannot
-- collide across tiers; we intentionally do NOT rebuild that generated column
-- (SQLite cannot ALTER it in place). Non-PrizePicks rows stay 'standard'.
ALTER TABLE prop_lines ADD COLUMN odds_type TEXT NOT NULL DEFAULT 'standard';

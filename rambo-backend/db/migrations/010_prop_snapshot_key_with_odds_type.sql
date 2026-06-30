-- Rebuild prop_lines table to include odds_type in snapshot_key.
-- This allows multiple tiers (goblin/standard/demon) of the same stat to coexist
-- even if they share the same line value. Without this, inserts collide on snapshot_key.
--
-- Strategy: Rename old table, create new one with updated snapshot_key, migrate data.

ALTER TABLE prop_lines RENAME TO prop_lines_old;

CREATE TABLE prop_lines (
    id              INTEGER PRIMARY KEY,
    game_pk         INTEGER REFERENCES games(game_pk) ON DELETE SET NULL,
    mlb_id          INTEGER REFERENCES players(mlb_id) ON DELETE SET NULL,
    book            TEXT    NOT NULL,
    market          TEXT    NOT NULL,        -- batter_hits | pitcher_strikeouts | ...
    line            REAL    NOT NULL,
    over_price      INTEGER,                 -- american; null for Pick6-style
    under_price     INTEGER,
    multiplier      REAL,                    -- Pick6 / PrizePicks-style payout
    player_name_raw TEXT,                    -- original book name, for resolution
    captured_at     TEXT    NOT NULL,
    odds_type       TEXT    NOT NULL DEFAULT 'standard',
    snapshot_key    TEXT GENERATED ALWAYS AS (
        book || '|' || market || '|' ||
        COALESCE(CAST(mlb_id AS TEXT), player_name_raw) || '|' || line || '|' ||
        COALESCE(over_price, '') || '|' || COALESCE(under_price, '') || '|' ||
        COALESCE(multiplier, '') || '|' || odds_type || '|' ||
        substr(captured_at, 1, 16)
    ) STORED,
    UNIQUE(snapshot_key)
) STRICT;

-- Migrate all data from old table (odds_type defaults to 'standard' for existing rows)
INSERT INTO prop_lines (id, game_pk, mlb_id, book, market, line, over_price,
                        under_price, multiplier, player_name_raw, captured_at, odds_type)
SELECT id, game_pk, mlb_id, book, market, line, over_price, under_price,
       multiplier, player_name_raw, captured_at, COALESCE(odds_type, 'standard')
FROM prop_lines_old;

-- Restore indexes
CREATE INDEX IF NOT EXISTS ix_prop_game   ON prop_lines(game_pk, market, captured_at);
CREATE INDEX IF NOT EXISTS ix_prop_player ON prop_lines(mlb_id);

-- Drop old table
DROP TABLE prop_lines_old;

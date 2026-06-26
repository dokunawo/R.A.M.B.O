-- ============================================================================
-- R.A.M.B.O. MLB Betting Agent — Ingestion Schema (Step 3)
-- Migration: 001_mlb_ingest_schema.sql
-- Target: SQLite 3.37+  (STRICT tables + generated columns required)
--
-- Run with foreign keys ON at the connection level:
--   PRAGMA foreign_keys = ON;
--   PRAGMA journal_mode = WAL;     -- better concurrency for scheduled pulls
--
-- Design principles:
--   * Raw lands first (raw_ingest), normalization is a separate pass.
--   * mlb_id (MLBAM id) is the canonical anchor for every player.
--   * Cross-feed IDs live in player_aliases; unmatched players go to
--     player_review for manual reconciliation — never guessed silently.
--   * Current-state tables (games, players) UPSERT.
--   * Line tables (odds_lines, prop_lines) are append-only snapshots, deduped
--     to the minute via a STORED generated snapshot_key so line movement is
--     preserved but identical re-pulls don't bloat the table.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- 0. RAW LANDING ZONE
-- Every dataset item from every actor lands here untouched, first.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw_ingest (
    id            INTEGER PRIMARY KEY,
    actor_id      TEXT    NOT NULL,          -- e.g. 'parseforge/espn-mlb-scoreboard-scraper'
    run_id        TEXT    NOT NULL,          -- Apify run id
    item_index    INTEGER NOT NULL,          -- position within the dataset
    payload       TEXT    NOT NULL,          -- raw item as JSON text
    payload_hash  TEXT    NOT NULL,          -- app-computed sha256 of payload
    scraped_at    TEXT    NOT NULL,          -- ISO8601 UTC
    UNIQUE(run_id, item_index)
) STRICT;

CREATE INDEX IF NOT EXISTS ix_raw_hash  ON raw_ingest(payload_hash);
CREATE INDEX IF NOT EXISTS ix_raw_actor ON raw_ingest(actor_id, scraped_at);


-- ----------------------------------------------------------------------------
-- 1. PLAYERS (canonical) + cross-feed ID map
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS players (
    mlb_id          INTEGER PRIMARY KEY,     -- canonical MLBAM id
    full_name       TEXT    NOT NULL,
    position        TEXT,
    bats            TEXT,                    -- L / R / S
    throws          TEXT,                    -- L / R
    birth_date      TEXT,
    country         TEXT,
    current_team_id INTEGER,
    updated_at      TEXT    NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS player_aliases (
    id               INTEGER PRIMARY KEY,
    mlb_id           INTEGER NOT NULL REFERENCES players(mlb_id) ON DELETE CASCADE,
    source           TEXT    NOT NULL,       -- 'bbref' | 'dk' | 'fd' | book code...
    source_player_id TEXT    NOT NULL,
    source_name      TEXT,
    confidence       REAL    NOT NULL DEFAULT 1.0,
    created_at       TEXT    NOT NULL,
    UNIQUE(source, source_player_id)         -- one alias per (source, id)
) STRICT;

CREATE INDEX IF NOT EXISTS ix_alias_mlb ON player_aliases(mlb_id);

-- Anything the ID resolver can't match with high confidence lands here.
CREATE TABLE IF NOT EXISTS player_review (
    id               INTEGER PRIMARY KEY,
    source           TEXT    NOT NULL,
    source_player_id TEXT    NOT NULL,
    source_name      TEXT,
    candidate_mlb_id INTEGER,                -- best guess (nullable)
    candidate_score  REAL,                   -- match confidence
    raw_ingest_id    INTEGER REFERENCES raw_ingest(id) ON DELETE SET NULL,
    status           TEXT    NOT NULL DEFAULT 'pending',  -- pending|resolved|rejected
    created_at       TEXT    NOT NULL,
    UNIQUE(source, source_player_id)
) STRICT;


-- ----------------------------------------------------------------------------
-- 2. GAMES (schedule + final state) — UPSERT target
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS games (
    game_pk           INTEGER PRIMARY KEY,
    official_date     TEXT    NOT NULL,
    season            INTEGER,
    game_type         TEXT,                  -- R/F/D/L/W/A
    status_detail     TEXT,
    home_team_id      INTEGER,
    home_team_name    TEXT,
    away_team_id      INTEGER,
    away_team_name    TEXT,
    home_score        INTEGER,
    away_score        INTEGER,
    venue_id          INTEGER,
    venue_name        TEXT,
    day_night         TEXT,
    double_header     TEXT,
    scheduled_innings INTEGER,
    url               TEXT,
    scraped_at        TEXT    NOT NULL
) STRICT;

CREATE INDEX IF NOT EXISTS ix_games_date   ON games(official_date);
CREATE INDEX IF NOT EXISTS ix_games_season ON games(season);


-- ----------------------------------------------------------------------------
-- 3. PLAYER STATS — season aggregates + per-game logs
-- Stats kept as JSON so new metrics never require a migration. The EV brain
-- reads them; it never touches raw_ingest.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS player_season_stats (
    id          INTEGER PRIMARY KEY,
    mlb_id      INTEGER NOT NULL REFERENCES players(mlb_id) ON DELETE CASCADE,
    season      INTEGER NOT NULL,
    stat_group  TEXT    NOT NULL,            -- hitting | pitching | fielding
    stats       TEXT    NOT NULL,            -- JSON: {metric: value}
    source      TEXT    NOT NULL,            -- mlb | bbref
    as_of_date  TEXT    NOT NULL,
    scraped_at  TEXT    NOT NULL,
    UNIQUE(mlb_id, season, stat_group, source, as_of_date)
) STRICT;

CREATE INDEX IF NOT EXISTS ix_season_player ON player_season_stats(mlb_id, season);

-- The granular table props research actually lives on (L10/L15, vs-pitcher).
CREATE TABLE IF NOT EXISTS player_game_logs (
    id               INTEGER PRIMARY KEY,
    mlb_id           INTEGER NOT NULL REFERENCES players(mlb_id) ON DELETE CASCADE,
    game_pk          INTEGER REFERENCES games(game_pk) ON DELETE SET NULL,
    game_date        TEXT    NOT NULL,
    stat_group       TEXT    NOT NULL,       -- hitting | pitching
    opponent_team_id INTEGER,
    is_home          INTEGER,                -- 0 / 1
    stats            TEXT    NOT NULL,       -- JSON per-game line
    source           TEXT    NOT NULL,
    scraped_at       TEXT    NOT NULL,
    UNIQUE(mlb_id, game_date, stat_group, source)
) STRICT;

CREATE INDEX IF NOT EXISTS ix_log_player ON player_game_logs(mlb_id, game_date);


-- ----------------------------------------------------------------------------
-- 4. GAME-LINE ODDS — append-only snapshots (preserves line movement)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS odds_lines (
    id           INTEGER PRIMARY KEY,
    game_pk      INTEGER REFERENCES games(game_pk) ON DELETE SET NULL,
    book         TEXT    NOT NULL,
    market       TEXT    NOT NULL,           -- moneyline | spread | total
    side         TEXT    NOT NULL,           -- home | away | over | under
    line         REAL,                       -- null for moneyline
    price        INTEGER NOT NULL,           -- american odds
    captured_at  TEXT    NOT NULL,
    -- dedupes identical lines pulled in the same minute; new price/line = new row
    snapshot_key TEXT GENERATED ALWAYS AS (
        game_pk || '|' || book || '|' || market || '|' || side || '|' ||
        COALESCE(line, '') || '|' || price || '|' || substr(captured_at, 1, 16)
    ) STORED,
    UNIQUE(snapshot_key)
) STRICT;

CREATE INDEX IF NOT EXISTS ix_odds_game ON odds_lines(game_pk, market, captured_at);


-- ----------------------------------------------------------------------------
-- 5. PLAYER PROP LINES — append-only snapshots
-- mlb_id is nullable until the ID resolver links the book's player.
-- player_name_raw is preserved so resolution can run after the fact.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS prop_lines (
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
    snapshot_key    TEXT GENERATED ALWAYS AS (
        book || '|' || market || '|' ||
        COALESCE(CAST(mlb_id AS TEXT), player_name_raw) || '|' || line || '|' ||
        COALESCE(over_price, '') || '|' || COALESCE(under_price, '') || '|' ||
        COALESCE(multiplier, '') || '|' || substr(captured_at, 1, 16)
    ) STORED,
    UNIQUE(snapshot_key)
) STRICT;

CREATE INDEX IF NOT EXISTS ix_prop_game   ON prop_lines(game_pk, market, captured_at);
CREATE INDEX IF NOT EXISTS ix_prop_player ON prop_lines(mlb_id);


-- ----------------------------------------------------------------------------
-- 6. CONVENIENCE VIEW — most recent line per game/book/market/side
-- The EV brain reads this instead of windowing the full history every time.
-- ----------------------------------------------------------------------------
CREATE VIEW IF NOT EXISTS v_latest_odds AS
SELECT o.*
FROM odds_lines o
JOIN (
    SELECT game_pk, book, market, side, MAX(captured_at) AS mx
    FROM odds_lines
    GROUP BY game_pk, book, market, side
) last
  ON  o.game_pk = last.game_pk
  AND o.book    = last.book
  AND o.market  = last.market
  AND o.side    = last.side
  AND o.captured_at = last.mx;

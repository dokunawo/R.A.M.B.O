-- Confirmed lineups (statsapi boxscore battingOrder). Presence = confirmed starter.
CREATE TABLE IF NOT EXISTS game_lineups (
    game_pk       INTEGER NOT NULL,
    team_id       INTEGER,
    mlb_id        INTEGER NOT NULL,
    batting_order INTEGER,          -- 100..900 (slot = order/100)
    side          TEXT,             -- 'home' | 'away'
    scraped_at    TEXT NOT NULL,
    PRIMARY KEY (game_pk, mlb_id)
) STRICT;

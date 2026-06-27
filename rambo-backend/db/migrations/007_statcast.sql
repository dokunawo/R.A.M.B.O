-- Statcast batter power quality (Baseball Savant) for the HR model.
CREATE TABLE IF NOT EXISTS player_statcast (
    mlb_id      INTEGER NOT NULL,
    season      INTEGER NOT NULL,
    barrel_rate REAL,                -- barrel_batted_rate %
    hard_hit    REAL,                -- hard_hit_percent %
    source      TEXT NOT NULL,
    scraped_at  TEXT NOT NULL,
    PRIMARY KEY (mlb_id, season)
) STRICT;

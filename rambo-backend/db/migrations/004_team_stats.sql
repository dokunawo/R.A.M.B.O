-- Team season runs scored/allowed for the moneyline Pythagorean model.
CREATE TABLE IF NOT EXISTS team_season_stats (
    team_id       INTEGER NOT NULL,
    season        INTEGER NOT NULL,
    runs_scored   INTEGER,
    runs_allowed  INTEGER,
    games_played  INTEGER,
    source        TEXT    NOT NULL,
    scraped_at    TEXT    NOT NULL,
    PRIMARY KEY (team_id, season)
) STRICT;

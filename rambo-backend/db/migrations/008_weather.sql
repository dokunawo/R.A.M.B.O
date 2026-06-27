-- Per-game weather (statsapi live feed) for the HR model.
CREATE TABLE IF NOT EXISTS game_weather (
    game_pk    INTEGER PRIMARY KEY,
    temp       INTEGER,             -- °F
    condition  TEXT,
    wind       TEXT,                -- e.g. "8 mph, Out To CF" (park-relative)
    scraped_at TEXT NOT NULL
) STRICT;

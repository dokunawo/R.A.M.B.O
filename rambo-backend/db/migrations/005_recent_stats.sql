-- Last-N-day recency stats (statsapi byDateRange leaderboard) for recency-aware models.
CREATE TABLE IF NOT EXISTS player_recent_stats (
    mlb_id      INTEGER NOT NULL,
    window      TEXT    NOT NULL,   -- 'L15'
    stat_group  TEXT    NOT NULL,   -- 'hitting' | 'pitching'
    stats       TEXT    NOT NULL,   -- JSON stat dict (homeRuns, hits, runs, rbi, ...)
    start_date  TEXT,
    end_date    TEXT,
    source      TEXT    NOT NULL,
    scraped_at  TEXT    NOT NULL,
    PRIMARY KEY (mlb_id, window, stat_group)
) STRICT;

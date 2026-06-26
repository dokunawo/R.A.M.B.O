-- Probable pitchers + team abbreviations on games, for the EV Brain's
-- handedness split and park lookup. The schedule pull already hydrates these.
ALTER TABLE games ADD COLUMN home_probable_pitcher_id INTEGER;
ALTER TABLE games ADD COLUMN away_probable_pitcher_id INTEGER;
ALTER TABLE games ADD COLUMN home_team_abbr TEXT;
ALTER TABLE games ADD COLUMN away_team_abbr TEXT;

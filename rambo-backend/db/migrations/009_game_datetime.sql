-- First-pitch timestamp (statsapi schedule gameDate) for game-time ordering.
ALTER TABLE games ADD COLUMN game_datetime TEXT;

-- ============================================================================
-- R.A.M.B.O. MLB Betting Agent — Migration 002
-- 002_normalize_watermark.sql
-- Adds a per-row watermark so the normalization pass processes each raw item
-- once. NULL = not yet normalized (or deliberately reset for reprocessing).
-- ============================================================================

ALTER TABLE raw_ingest ADD COLUMN normalized_at TEXT;

CREATE INDEX IF NOT EXISTS ix_raw_unnormalized
    ON raw_ingest(actor_id) WHERE normalized_at IS NULL;

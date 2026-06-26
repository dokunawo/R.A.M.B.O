"""
R.A.M.B.O. MLB Betting Agent — Raw landing (Step 3)
ingestion/raw_store.py

Takes a RunResult from the Apify wrapper and writes every item into raw_ingest,
untouched. Idempotent: re-landing the same run is a no-op. No parsing here —
normalization reads raw_ingest in a later pass.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from ingestion.apify_client_wrapper import ActorConfig, RunResult, run_actor


def _canonical(item: dict[str, Any]) -> str:
    """Stable JSON for hashing + storage (sorted keys, compact)."""
    return json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def land_raw(
    conn: sqlite3.Connection,
    run: RunResult,
    scraped_at: str | None = None,
) -> dict[str, int]:
    """Insert each item of `run` into raw_ingest. Returns {inserted, skipped}.

    Idempotency: UNIQUE(run_id, item_index) means re-landing the same run skips
    rather than duplicates. Identical content from a *different* run is kept on
    purpose — for line tables that's a new capture, not a duplicate."""
    scraped_at = scraped_at or datetime.now(timezone.utc).isoformat()
    inserted = skipped = 0

    conn.execute("BEGIN;")
    try:
        for idx, item in enumerate(run.items):
            payload = _canonical(item)
            cur = conn.execute(
                """INSERT INTO raw_ingest
                     (actor_id, run_id, item_index, payload, payload_hash, scraped_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(run_id, item_index) DO NOTHING;""",
                (run.actor_id, run.run_id, idx, payload, _hash(payload), scraped_at),
            )
            if cur.rowcount == 1:
                inserted += 1
            else:
                skipped += 1
        conn.execute("COMMIT;")
    except Exception:
        conn.execute("ROLLBACK;")
        raise

    return {"inserted": inserted, "skipped": skipped}


def pull_and_land(
    conn: sqlite3.Connection,
    cfg: ActorConfig,
    run_input: dict[str, Any],
) -> dict[str, Any]:
    """Seam between Step 2 and Step 3 (used by the Step 5 endpoint/CLI):
    run the actor, land raw, return a small summary. Normalization runs
    separately against raw_ingest."""
    result = run_actor(cfg, run_input)
    landed = land_raw(conn, result)
    return {
        "actor_id": result.actor_id,
        "run_id": result.run_id,
        "items": result.item_count,
        "estimated_cost_usd": result.estimated_cost_usd,
        **landed,
    }

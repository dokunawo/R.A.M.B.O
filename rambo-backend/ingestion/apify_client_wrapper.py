"""
R.A.M.B.O. MLB Betting Agent — Apify Client Wrapper (Step 2)
ingestion/apify_client_wrapper.py

Single responsibility: run an Apify actor and return its dataset items, with
spend capped *before* the run starts. No parsing, no normalization, no DB writes
— that's the ingestion/normalization layers' job.

Guardrails:
  * Per-actor maxItems cap (clamps whatever the caller passes).
  * Pre-flight spend guard: worst-case cost (cap / 1000 * price) is computed
    before the run; if it exceeds max_cost_usd the run is refused, not attempted.
  * Retry with exponential backoff on transient failures.
  * Hard run timeout.
  * Logs item count + ESTIMATED cost per run (estimate only — Apify's invoice
    is authoritative).

Dependency: apify-client  (pip install apify-client)
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any, Optional

from apify_client import ApifyClient

logger = logging.getLogger("rambo.ingestion.apify")


class ApifyIngestError(RuntimeError):
    """Raised when a run cannot be completed or would breach a guardrail."""


@dataclass(frozen=True)
class ActorConfig:
    """Per-actor settings. Lives in config/apify.py; passed in here so this
    module stays decoupled from configuration."""
    actor_id: str
    max_items: int                  # hard ceiling on dataset items pulled
    price_per_1k: float             # $ per 1,000 results (for cost estimate)
    max_cost_usd: float = 5.00      # pre-flight spend guard per run
    memory_mbytes: int = 1024
    run_timeout_secs: int = 300     # max actor run duration


@dataclass
class RunResult:
    """Richer than a bare list so the raw-landing layer has run_id + dataset_id
    for raw_ingest. (Deviates from the 'returns list[dict]' note on purpose —
    Step 3 needs the run metadata.)"""
    actor_id: str
    run_id: str
    dataset_id: str
    items: list[dict[str, Any]]
    item_count: int
    estimated_cost_usd: float


def get_client(token: Optional[str] = None) -> ApifyClient:
    token = token or os.environ.get("APIFY_TOKEN")
    if not token:
        raise ApifyIngestError("APIFY_TOKEN is not set — check your .env")
    return ApifyClient(token)


def _estimate_cost(item_count: int, price_per_1k: float) -> float:
    return round(item_count / 1000.0 * price_per_1k, 4)


def _extract(run: Any, *names: str) -> Any:
    """Read a field from the run whether the SDK returns a dict (older clients) or
    a model object (apify-client 3.x). Tolerates snake_case vs camelCase."""
    for n in names:
        if isinstance(run, dict) and n in run:
            return run[n]
        if hasattr(run, n):
            return getattr(run, n)
    return None


def run_actor(
    cfg: ActorConfig,
    run_input: dict[str, Any],
    *,
    client: Optional[ApifyClient] = None,
    max_retries: int = 3,
    base_backoff: float = 2.0,
) -> RunResult:
    """Run one actor, enforce caps, return items + run metadata."""
    client = client or get_client()

    # 1. Clamp maxItems to the per-actor ceiling (caller can only go lower).
    requested = int(run_input.get("maxItems", cfg.max_items))
    capped = min(requested, cfg.max_items)
    run_input = {**run_input, "maxItems": capped}

    # 2. Pre-flight spend guard — refuse before spending a credit.
    worst_case = _estimate_cost(capped, cfg.price_per_1k)
    if worst_case > cfg.max_cost_usd:
        raise ApifyIngestError(
            f"{cfg.actor_id}: worst-case ${worst_case:.2f} exceeds "
            f"max_cost_usd ${cfg.max_cost_usd:.2f} (maxItems={capped}). Refusing run."
        )

    # 3. Launch with retry/backoff — ONLY the .call() is retried. A failure AFTER a
    #    successful run (e.g. parsing the dataset) must NEVER re-run a paid actor.
    last_err: Optional[Exception] = None
    run: Any = None
    for attempt in range(1, max_retries + 1):
        try:
            # apify-client 3.x: run_timeout is a timedelta; max_items caps results
            # API-side (don't trust the actor to honor the input field); and
            # max_total_charge_usd is a HARD, Apify-enforced spend ceiling — even a
            # runaway actor can't bill past it.
            run = client.actor(cfg.actor_id).call(
                run_input=run_input,
                max_items=capped,
                memory_mbytes=cfg.memory_mbytes,
                run_timeout=timedelta(seconds=cfg.run_timeout_secs),
                max_total_charge_usd=Decimal(str(cfg.max_cost_usd)),
            )
            break  # launched + finished; do NOT retry past this point
        except Exception as err:  # transient: network, 5xx, launch failure
            last_err = err
            if attempt == max_retries:
                raise ApifyIngestError(
                    f"{cfg.actor_id}: failed after {max_retries} attempts: {last_err}"
                ) from last_err
            backoff = base_backoff ** attempt
            logger.warning("actor=%s attempt=%d/%d failed: %s — retrying in %.1fs",
                           cfg.actor_id, attempt, max_retries, err, backoff)
            time.sleep(backoff)

    # 4. Parse OUTSIDE the retry loop — the run already executed; never re-run it.
    status = _extract(run, "status")
    status_str = getattr(status, "value", status)  # ActorJobStatus enum -> str
    if run is None or str(status_str) != "SUCCEEDED":
        raise ApifyIngestError(f"{cfg.actor_id}: run status {status_str}")

    dataset_id = _extract(run, "default_dataset_id", "defaultDatasetId")
    run_id = _extract(run, "id")
    items: list[dict[str, Any]] = []
    for item in client.dataset(dataset_id).iterate_items():  # cap iteration too
        items.append(item)
        if len(items) >= capped:
            break

    cost = _estimate_cost(len(items), cfg.price_per_1k)
    logger.info("actor=%s run=%s items=%d est_cost=$%.4f (cap=%d)",
                cfg.actor_id, run_id, len(items), cost, capped)
    return RunResult(
        actor_id=cfg.actor_id, run_id=run_id, dataset_id=dataset_id,
        items=items, item_count=len(items), estimated_cost_usd=cost,
    )

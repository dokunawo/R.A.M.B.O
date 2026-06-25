import logging

logger = logging.getLogger(__name__)

# Anthropic published rates — cost per million tokens.
# Pricing changes over time; update this table when rates change.
# Source: https://docs.anthropic.com/en/docs/about-claude/models
MODEL_PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4": {
        "input":        3.00,
        "output":      15.00,
        "cache_write":  3.75,
        "cache_read":   0.30,
    },
    "claude-opus-4": {
        "input":       15.00,
        "output":      75.00,
        "cache_write": 18.75,
        "cache_read":   1.50,
    },
    "claude-haiku-3.5": {
        "input":        0.80,
        "output":       4.00,
        "cache_write":  1.00,
        "cache_read":   0.08,
    },
    "claude-sonnet-3.5": {
        "input":        3.00,
        "output":      15.00,
        "cache_write":  3.75,
        "cache_read":   0.30,
    },
    # Voyage AI embeddings — flat per-million-token rate (no output/cache tiers).
    # First 200M tokens/account are free; these rates apply beyond that.
    # Source: https://docs.voyageai.com/docs/pricing
    "voyage-4-lite": {
        "input":        0.02,
        "output":       0.00,
        "cache_write":  0.00,
        "cache_read":   0.00,
    },
    "voyage-4": {
        "input":        0.06,
        "output":       0.00,
        "cache_write":  0.00,
        "cache_read":   0.00,
    },
    "voyage-4-large": {
        "input":        0.12,
        "output":       0.00,
        "cache_write":  0.00,
        "cache_read":   0.00,
    },
}

_PER_MILLION = 1_000_000


def _resolve_model(model: str) -> dict[str, float] | None:
    """Longest-prefix match against MODEL_PRICING keys."""
    if model in MODEL_PRICING:
        return MODEL_PRICING[model]
    best_key = ""
    for key in MODEL_PRICING:
        if model.startswith(key) and len(key) > len(best_key):
            best_key = key
    if best_key:
        return MODEL_PRICING[best_key]
    return None


def compute_cost(
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
) -> float:
    rates = _resolve_model(model)
    if rates is None:
        logger.warning("Unknown model %r — recording 0 cost", model)
        return 0.0

    return (
        input_tokens * rates["input"]
        + output_tokens * rates["output"]
        + cache_creation_input_tokens * rates["cache_write"]
        + cache_read_input_tokens * rates["cache_read"]
    ) / _PER_MILLION

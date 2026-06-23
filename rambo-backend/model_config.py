"""Central model configuration.

One source of truth for the default LLM model id, so a model deprecation is a
one-line change (or a single env var) instead of a hunt across call sites.

The previous hardcoded `claude-sonnet-4-20250514` is deprecated and 404s on
current accounts. Default is now `claude-sonnet-4-6`. Override with RAMBO_MODEL.
"""

from __future__ import annotations

import os

DEFAULT_MODEL = "claude-sonnet-4-6"


def default_model() -> str:
    return os.environ.get("RAMBO_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL

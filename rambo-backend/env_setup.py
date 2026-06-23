"""Load environment variables from rambo-backend/.env at startup.

Must be imported and run BEFORE anything that reads os.environ (notably the
orchestrator, which checks ANTHROPIC_API_KEY at import time).

Dependency-optional: uses python-dotenv if installed, otherwise falls back to a
minimal built-in parser so the .env is honored even without the package.
Existing environment variables are never overwritten (real env > .env file).
"""

from __future__ import annotations

import os
from pathlib import Path

_ENV_PATH = Path(__file__).resolve().parent / ".env"


def _fallback_parse(path: Path) -> None:
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_env() -> bool:
    """Load .env if it exists. Returns True if a file was found."""
    if not _ENV_PATH.exists():
        return False
    try:
        from dotenv import load_dotenv
        load_dotenv(_ENV_PATH, override=False)
    except ImportError:
        _fallback_parse(_ENV_PATH)
    return True

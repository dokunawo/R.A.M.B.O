"""Input sanitization for Factory prompt generation.

Strips control characters and injection patterns from user-supplied
role descriptions before they reach LLM prompts.
"""

from __future__ import annotations

import re

_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"system\s*:", re.IGNORECASE),
    re.compile(r"```\s*system", re.IGNORECASE),
    re.compile(r"<\s*system\s*>", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+in", re.IGNORECASE),
    re.compile(r"disregard\s+(?:all\s+)?(?:prior|above)", re.IGNORECASE),
    re.compile(r"override\s+(?:your\s+)?(?:instructions|prompt)", re.IGNORECASE),
    re.compile(r"exfiltrate", re.IGNORECASE),
]

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_role_input(text: str) -> str:
    """Strip control chars and flag injection attempts.

    Raises ValueError if the text contains injection patterns.
    """
    cleaned = _CONTROL_CHAR_RE.sub("", text)
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(cleaned):
            raise ValueError(
                f"Input rejected: contains suspicious pattern ({pattern.pattern})"
            )
    return cleaned.strip()

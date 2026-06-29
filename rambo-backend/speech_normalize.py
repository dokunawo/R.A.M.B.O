"""Expand abbreviations to spoken form before TTS so the neural voice says
"miles per hour" instead of garbling "mph".

Curated + word-boundary matched: team codes (ATL/NYY) and ambiguous bare letters
(K) are left untouched, and real English words ("in", "so") are never mangled.
Pure stdlib; never raises — returns the original text on any error, because the
voice path must never break.
"""
from __future__ import annotations

import re

# Ordered (compiled pattern, replacement). Most specific first. Word boundaries
# (\b) keep each rule from firing inside other tokens. Baseball acronyms are
# case-SENSITIVE (matched only as written caps) so a capitalized ordinary word
# like "So" can't turn into "strikeouts".
_RULES = [
    # ── units ────────────────────────────────────────────────────────────────
    (re.compile(r"°\s*F\b", re.I), " degrees Fahrenheit"),   # 75°F -> 75 degrees Fahrenheit
    (re.compile(r"°"), " degrees"),                          # 30°  -> 30 degrees
    (re.compile(r"\bmph\b", re.I), "miles per hour"),
    (re.compile(r"\blbs?\b", re.I), "pounds"),
    (re.compile(r"\boz\b", re.I), "ounces"),
    (re.compile(r"\bft\b", re.I), "feet"),
    # ── symbols ──────────────────────────────────────────────────────────────
    (re.compile(r"(\d)\s*\+"), r"\1 plus"),                  # 8+ -> 8 plus (alt-K ladder)
    (re.compile(r"%"), " percent"),
    (re.compile(r"\s*&\s*"), " and "),
    (re.compile(r"\s*@\s*"), " at "),
    (re.compile(r"\bvs\.?\b", re.I), "versus"),
    (re.compile(r"\bw/"), "with "),
    # ── baseball stats (caps as written) ─────────────────────────────────────
    (re.compile(r"\bERA\b"), "earned run average"),
    (re.compile(r"\bRBI\b"), "runs batted in"),
    (re.compile(r"\bHR\b"), "home runs"),
    (re.compile(r"\bSO\b"), "strikeouts"),
    (re.compile(r"\bBB\b"), "walks"),
    (re.compile(r"\bIP\b"), "innings pitched"),
    (re.compile(r"\bBF\b"), "batters faced"),
    (re.compile(r"\bAVG\b", re.I), "average"),
]


def normalize_for_speech(text):
    """Return `text` with known abbreviations expanded for natural TTS. Falsy or
    non-string input is returned unchanged. Never raises."""
    if not text or not isinstance(text, str):
        return text
    try:
        out = text
        for pattern, repl in _RULES:
            out = pattern.sub(repl, out)
        return re.sub(r"  +", " ", out)          # collapse doubles from replacements
    except Exception:
        return text

"""
Generates the integrations AUTO block by detecting configured services.
"""

from __future__ import annotations

import os


def generate() -> str:
    integrations = []

    # Anthropic Claude — check env var and importability
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    try:
        import anthropic
        has_lib = True
    except ImportError:
        has_lib = False
    integrations.append({
        "name": "Anthropic Claude",
        "purpose": "Voice layer — LLM for generating spoken responses",
        "status": "active" if (has_key and has_lib) else "configured" if has_lib else "missing sdk",
        "config": "`ANTHROPIC_API_KEY` env var",
    })

    # Open-Meteo — no key needed, check httpx
    try:
        import httpx
        has_httpx = True
    except ImportError:
        has_httpx = False
    integrations.append({
        "name": "Open-Meteo",
        "purpose": "Weather data — geocoding + forecast (no API key needed)",
        "status": "active" if has_httpx else "missing httpx",
        "config": "none (free API)",
    })

    # Google Calendar
    try:
        from google_calendar import calendar_skill
        gcal_status = "available"
    except ImportError:
        gcal_status = "scaffolded"
    integrations.append({
        "name": "Google Calendar",
        "purpose": "Read/write calendar events",
        "status": gcal_status,
        "config": "`credentials.json` + OAuth token",
    })

    # Google Drive
    try:
        from google_drive import drive_skill
        gdrive_status = "available"
    except ImportError:
        gdrive_status = "scaffolded"
    integrations.append({
        "name": "Google Drive",
        "purpose": "Search and access files in Drive",
        "status": gdrive_status,
        "config": "`credentials.json` + OAuth token",
    })

    lines = ["| Service | Purpose | Status | Config |", "| --- | --- | --- | --- |"]
    for i in integrations:
        lines.append(f"| {i['name']} | {i['purpose']} | {i['status']} | {i['config']} |")

    return "\n".join(lines)

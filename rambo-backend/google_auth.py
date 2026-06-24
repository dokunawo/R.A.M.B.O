"""Google OAuth2 helper — handles token acquisition and refresh for all Google integrations."""

import os
import json
import logging
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

log = logging.getLogger("rambo.google_auth")

BASE_DIR = Path(__file__).parent
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
TOKEN_FILE = BASE_DIR / "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


def get_credentials() -> Credentials | None:
    """Return valid Google credentials, refreshing if needed. Returns None if no
    token exists. Failures are logged (not swallowed silently)."""
    creds = None

    if not TOKEN_FILE.exists():
        log.warning("Google: no token.json — Link integration is OFFLINE (run /google/auth).")
        return None

    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN_FILE.write_text(creds.to_json())
        except Exception as e:
            log.error("Google: token refresh failed (re-auth needed): %s", e)
            creds = None
    elif creds and creds.expired and not creds.refresh_token:
        log.error("Google: token expired and no refresh_token — re-auth needed.")
        creds = None

    return creds


def integration_status() -> dict:
    """Detailed Link/Google status: CONNECTED / DEGRADED / OFFLINE + reason."""
    if not TOKEN_FILE.exists():
        return {"agent": "link", "service": "google", "status": "OFFLINE",
                "reason": "No token.json — authorize via /google/auth."}
    try:
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    except Exception as e:
        return {"agent": "link", "service": "google", "status": "DEGRADED",
                "reason": f"token.json unreadable: {e}"}
    if creds.valid:
        return {"agent": "link", "service": "google", "status": "CONNECTED", "scopes": SCOPES}
    if creds.expired and creds.refresh_token:
        return {"agent": "link", "service": "google", "status": "DEGRADED",
                "reason": "Token expired but refreshable (auto-refresh on next call)."}
    return {"agent": "link", "service": "google", "status": "OFFLINE",
            "reason": "Token expired and not refreshable — re-auth needed."}


def run_auth_flow(port: int = 8090) -> Credentials:
    """Run the OAuth consent flow — opens a browser for the user to authorize."""
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
    creds = flow.run_local_server(port=port, prompt="consent", access_type="offline")
    TOKEN_FILE.write_text(creds.to_json())
    return creds


def is_authenticated() -> bool:
    creds = get_credentials()
    return creds is not None and creds.valid

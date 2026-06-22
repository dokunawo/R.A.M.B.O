"""Google OAuth2 helper — handles token acquisition and refresh for all Google integrations."""

import os
import json
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

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
    """Return valid Google credentials, refreshing if needed. Returns None if no token exists."""
    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN_FILE.write_text(creds.to_json())
        except Exception:
            creds = None

    return creds


def run_auth_flow(port: int = 8090) -> Credentials:
    """Run the OAuth consent flow — opens a browser for the user to authorize."""
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
    creds = flow.run_local_server(port=port, prompt="consent", access_type="offline")
    TOKEN_FILE.write_text(creds.to_json())
    return creds


def is_authenticated() -> bool:
    creds = get_credentials()
    return creds is not None and creds.valid

"""Gmail read skill — summarize recent / unread / important mail.

Reuses the existing Google OAuth (google_auth) — the gmail.readonly scope is
already declared there. Read-only: it never sends or deletes.
"""
from google_auth import get_credentials

try:
    from googleapiclient.discovery import build
except ImportError:
    build = None


def _service():
    creds = get_credentials()
    if not creds or not creds.valid:
        return None
    return build("gmail", "v1", credentials=creds)


def _query_for(goal: str) -> tuple[str, str]:
    """Map the request to a Gmail search query + a human label."""
    g = goal.lower()
    if "important" in g:
        return "is:important is:unread", "important unread"
    if "today" in g:
        return "newer_than:1d", "from today"
    if "unread" in g or "new email" in g or "new mail" in g:
        return "is:unread", "unread"
    return "is:unread", "unread"


async def gmail_skill(goal: str, ctx: dict) -> str:
    if build is None:
        return "Google API client not installed. Add google-api-python-client to requirements."
    service = _service()
    if not service:
        return "Not authenticated with Google. Run /google/auth to connect your account."

    query, label = _query_for(goal)
    try:
        resp = service.users().messages().list(userId="me", q=query, maxResults=8).execute()
        msgs = resp.get("messages", [])
    except Exception as e:
        return f"Gmail error: {e}"

    if not msgs:
        return f"No {label} email."

    lines = [f"Email — {label} ({len(msgs)}):"]
    for m in msgs:
        try:
            full = service.users().messages().get(
                userId="me", id=m["id"], format="metadata",
                metadataHeaders=["From", "Subject"],
            ).execute()
            headers = {h["name"]: h["value"]
                       for h in full.get("payload", {}).get("headers", [])}
            frm = headers.get("From", "?")
            subj = headers.get("Subject", "(no subject)")
            snippet = (full.get("snippet", "") or "")[:90]
            lines.append(f"  • {subj} — {frm}\n    {snippet}")
        except Exception:
            continue
    return "\n".join(lines)

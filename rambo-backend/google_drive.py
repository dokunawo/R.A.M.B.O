"""Google Drive skill — search, list, and read files."""

import re
from google_auth import get_credentials

try:
    from googleapiclient.discovery import build
except ImportError:
    build = None


def _get_service():
    creds = get_credentials()
    if not creds or not creds.valid:
        return None
    return build("drive", "v3", credentials=creds)


async def drive_skill(goal: str, ctx: dict) -> str:
    if build is None:
        return "Google API client not installed."

    service = _get_service()
    if not service:
        return "Not authenticated with Google. Run /google/auth to connect your account."

    lower = goal.lower()

    # Search for specific files
    search_match = re.search(r'(?:find|search|look for|locate)\s+(?:file|doc|document|sheet|slide|folder)?\s*[:\-]?\s*(.+)', lower)
    if search_match:
        query = search_match.group(1).strip().strip("?.! ")
        return await _search_files(service, query)

    # List recent files
    return await _list_recent(service)


async def _list_recent(service) -> str:
    try:
        result = service.files().list(
            pageSize=15,
            fields="files(id, name, mimeType, modifiedTime, owners)",
            orderBy="modifiedTime desc",
        ).execute()
    except Exception as e:
        return f"Drive error: {e}"

    files = result.get("files", [])
    if not files:
        return "No files found in your Drive."

    lines = [f"Google Drive — recent files ({len(files)}):"]
    for f in files:
        name = f.get("name", "(untitled)")
        mime = f.get("mimeType", "")
        icon = _mime_icon(mime)
        modified = f.get("modifiedTime", "")[:10]
        lines.append(f"  {icon} {name}  ({modified})")

    return "\n".join(lines)


async def _search_files(service, query: str) -> str:
    try:
        result = service.files().list(
            q=f"name contains '{query}' and trashed = false",
            pageSize=10,
            fields="files(id, name, mimeType, modifiedTime, webViewLink)",
            orderBy="modifiedTime desc",
        ).execute()
    except Exception as e:
        return f"Drive search error: {e}"

    files = result.get("files", [])
    if not files:
        return f"No files matching \"{query}\" found."

    lines = [f"Drive search — \"{query}\" ({len(files)} results):"]
    for f in files:
        name = f.get("name", "(untitled)")
        mime = f.get("mimeType", "")
        icon = _mime_icon(mime)
        modified = f.get("modifiedTime", "")[:10]
        lines.append(f"  {icon} {name}  ({modified})")

    return "\n".join(lines)


def _mime_icon(mime: str) -> str:
    if "folder" in mime:
        return "📁"
    if "document" in mime:
        return "📄"
    if "spreadsheet" in mime:
        return "📊"
    if "presentation" in mime:
        return "📽️"
    if "pdf" in mime:
        return "📑"
    if "image" in mime:
        return "🖼️"
    return "📎"

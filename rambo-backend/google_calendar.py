"""Google Calendar skill — reads and creates events."""

import re
from datetime import datetime, timedelta

from google_auth import get_credentials

try:
    from googleapiclient.discovery import build
except ImportError:
    build = None


def _get_service():
    creds = get_credentials()
    if not creds or not creds.valid:
        return None
    return build("calendar", "v3", credentials=creds)


async def calendar_skill(goal: str, ctx: dict) -> str:
    if build is None:
        return "Google API client not installed. Add google-api-python-client to requirements."

    service = _get_service()
    if not service:
        return "Not authenticated with Google. Run /google/auth to connect your account."

    lower = goal.lower()

    # Create event
    if any(w in lower for w in ("schedule", "create event", "add event", "book", "set up a meeting", "add to calendar", "add to my calendar")):
        return await _create_event(service, goal)

    # List events (default)
    return await _list_events(service, goal, ctx)


async def _list_events(service, goal: str, ctx: dict | None = None) -> str:
    lower = goal.lower()

    # Prefer a centrally-resolved temporal range (from the orchestrator) so
    # "this week", "tomorrow", etc. resolve identically everywhere. Fall back to
    # the local keyword parsing below when none was attached.
    resolved = (ctx or {}).get("temporal") or []
    if resolved:
        r = resolved[0]
        time_min = r.start.isoformat() + "Z"
        time_max = r.end.isoformat() + "Z"
        return await _query_and_format(service, time_min, time_max, r.phrase)

    # Determine time range
    now = datetime.utcnow()
    if "tomorrow" in lower:
        start = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0)
        end = start + timedelta(days=1)
        label = "tomorrow"
    elif "this week" in lower or "week" in lower:
        start = now
        end = now + timedelta(days=7)
        label = "this week"
    elif "next week" in lower:
        days_until_monday = (7 - now.weekday()) % 7 or 7
        start = (now + timedelta(days=days_until_monday)).replace(hour=0, minute=0, second=0)
        end = start + timedelta(days=7)
        label = "next week"
    else:
        start = now
        end = now + timedelta(days=1)
        label = "today"

    time_min = start.isoformat() + "Z"
    time_max = end.isoformat() + "Z"
    return await _query_and_format(service, time_min, time_max, label)


async def _query_and_format(service, time_min: str, time_max: str, label: str) -> str:
    try:
        result = service.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            maxResults=15,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
    except Exception as e:
        return f"Calendar error: {e}"

    events = result.get("items", [])
    if not events:
        return f"No events {label}."

    lines = [f"Calendar — {label} ({len(events)} events):"]
    for ev in events:
        start_raw = ev["start"].get("dateTime", ev["start"].get("date", ""))
        try:
            dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
            time_str = dt.strftime("%I:%M %p")
        except Exception:
            time_str = start_raw
        summary = ev.get("summary", "(no title)")
        lines.append(f"  {time_str} — {summary}")

    return "\n".join(lines)


async def _create_event(service, goal: str) -> str:
    # Basic parsing — extract time and title from natural language
    # Examples: "schedule a meeting at 3pm called Team Sync"
    #           "add event tomorrow at 2pm Project Review"

    now = datetime.now()
    event_date = now

    if "tomorrow" in goal.lower():
        event_date = now + timedelta(days=1)

    # Try to find a time like "at 3pm", "at 14:00", "at 3:30pm"
    time_match = re.search(r'at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', goal, re.IGNORECASE)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)
        ampm = (time_match.group(3) or "").lower()
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        event_date = event_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
    else:
        event_date = event_date.replace(hour=now.hour + 1, minute=0, second=0, microsecond=0)

    # Extract title — strip common prefixes
    title = goal
    for prefix in ("schedule", "create event", "add event", "book", "set up a meeting", "add to calendar", "add to my calendar"):
        title = re.sub(rf'^.*?\b{prefix}\b\s*', '', title, flags=re.IGNORECASE)
    # Remove time references
    title = re.sub(r'\b(at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\b(tomorrow|today)\b', '', title, flags=re.IGNORECASE)
    # Clean up
    title = re.sub(r'\b(called|named|titled)\b\s*', '', title, flags=re.IGNORECASE)
    title = title.strip().strip(".,!? ") or "R.A.M.B.O Event"

    end_date = event_date + timedelta(hours=1)

    event_body = {
        "summary": title,
        "start": {"dateTime": event_date.isoformat(), "timeZone": "America/Detroit"},
        "end": {"dateTime": end_date.isoformat(), "timeZone": "America/Detroit"},
    }

    try:
        created = service.events().insert(calendarId="primary", body=event_body).execute()
        time_str = event_date.strftime("%I:%M %p on %m/%d/%Y")
        return f"Event created: \"{created.get('summary')}\" at {time_str}"
    except Exception as e:
        return f"Failed to create event: {e}"

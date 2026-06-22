# skills.py — a small, scalable "skill" layer for R.A.M.B.O.
#
# Each skill declares: a name, the agent that runs it, a matcher (does this goal
# apply?), and an async run() that can call real external services. The
# orchestrator checks skills first; new real-world capabilities are added simply
# by appending to SKILLS — no other code changes needed.

import re

try:
    import httpx
except ImportError:
    httpx = None

try:
    from google_calendar import calendar_skill as _calendar_skill
    _HAS_GCAL = True
except ImportError:
    _HAS_GCAL = False


WEATHER_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "rime fog",
    51: "light drizzle", 53: "drizzle", 55: "dense drizzle",
    56: "freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    66: "freezing rain", 67: "heavy freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "rain showers", 81: "rain showers", 82: "violent rain showers",
    85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with heavy hail",
}


async def _geocode(city: str):
    """City name → (lat, lon, label) using Open-Meteo's free geocoder (no key)."""
    if httpx is None:
        return None
    url = "https://geocoding-api.open-meteo.com/v1/search"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, params={"name": city, "count": 1})
            data = r.json()
    except Exception:
        return None
    results = data.get("results") or []
    if not results:
        return None
    g = results[0]
    label = g.get("name", city)
    if g.get("admin1"):
        label += f", {g['admin1']}"
    if g.get("country_code"):
        label += f" ({g['country_code']})"
    return g["latitude"], g["longitude"], label


async def weather_skill(goal: str, ctx: dict) -> str:
    if httpx is None:
        return "Weather lookups need the 'httpx' package installed on the backend."

    # 1) explicit city in the goal ("...in Detroit", "...for Tokyo")
    lat = lon = label = None
    m = re.search(r"\b(?:in|at|for|near|around)\s+([A-Za-z .,'\-]+)", goal)
    if m:
        city = m.group(1).strip().strip("?.! ")
        geo = await _geocode(city)
        if geo:
            lat, lon, label = geo

    # 2) otherwise fall back to the operator's browser location
    if lat is None and ctx.get("lat") is not None and ctx.get("lon") is not None:
        lat, lon, label = ctx["lat"], ctx["lon"], "your location"

    if lat is None:
        return ("I couldn't resolve a location. Try \"weather in <city>\", "
                "or allow location access so I can use where you are.")

    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code",
        "temperature_unit": "fahrenheit", "wind_speed_unit": "mph",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, params=params)
            d = r.json()
    except Exception as e:
        return f"Weather service unreachable: {e}"

    c = d.get("current") or {}
    cond = WEATHER_CODES.get(c.get("weather_code"), "unknown conditions")
    return (
        f"Weather — {label}\n"
        f"  {cond}\n"
        f"  {c.get('temperature_2m')}°F (feels like {c.get('apparent_temperature')}°F)\n"
        f"  humidity {c.get('relative_humidity_2m')}%  ·  wind {c.get('wind_speed_10m')} mph"
    )


# The registry. Add new real-world skills here.
SKILLS = [
    {
        "name": "weather",
        "agent": "seeker",
        "match": lambda g: any(w in g.lower() for w in ("weather", "temperature", "forecast", "how hot", "how cold")),
        "run": weather_skill,
    },
]

if _HAS_GCAL:
    SKILLS.append({
        "name": "calendar",
        "agent": "pilot",
        "match": lambda g: any(w in g.lower() for w in (
            "calendar", "schedule", "event", "meeting", "appointment",
            "what's on my", "what do i have", "my day", "my week",
            "book a", "set up a meeting", "add to my calendar",
        )),
        "run": _calendar_skill,
    })


def match_skill(goal: str):
    for s in SKILLS:
        try:
            if s["match"](goal):
                return s
        except Exception:
            continue
    return None

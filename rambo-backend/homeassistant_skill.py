"""Home Assistant smart-home control — gated on HASS_URL + HASS_TOKEN.

Turns devices on/off by friendly-name match and reports state. Degrades
gracefully (clear message) when Home Assistant isn't configured, so it's safe to
register even if you don't run HA.

Env:
  HASS_URL    base URL of your Home Assistant (e.g. http://homeassistant.local:8123)
  HASS_TOKEN  a long-lived access token
"""
import os
import re

try:
    import httpx
except ImportError:
    httpx = None

# Domains we know how to toggle, in priority order when matching by name.
_TOGGLEABLE = ("light", "switch", "fan", "input_boolean", "climate", "lock")


def _config() -> tuple[str, str]:
    return os.environ.get("HASS_URL", "").rstrip("/"), os.environ.get("HASS_TOKEN", "")


def is_configured() -> bool:
    url, tok = _config()
    return bool(url and tok)


def _headers(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _parse_intent(goal: str) -> tuple[str | None, str]:
    """Return (action, target_name). action is 'on'/'off'/None (status)."""
    g = goal.lower()
    action = None
    if re.search(r"\b(turn on|switch on|enable|activate)\b", g):
        action = "on"
    elif re.search(r"\b(turn off|switch off|disable|deactivate|shut off)\b", g):
        action = "off"
    # Strip command words to leave the device name.
    name = re.sub(
        r"\b(turn on|turn off|switch on|switch off|enable|disable|activate|"
        r"deactivate|shut off|the|my|please|in the|all)\b", " ", g)
    name = re.sub(r"\s+", " ", name).strip(" ?.!")
    return action, name


async def homeassistant_skill(goal: str, ctx: dict) -> str:
    if httpx is None:
        return "httpx not installed on the backend."
    url, tok = _config()
    if not (url and tok):
        return ("Home Assistant isn't configured. Set HASS_URL and HASS_TOKEN on "
                "the backend to enable smart-home control.")

    action, name = _parse_intent(goal)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            states = (await client.get(f"{url}/api/states", headers=_headers(tok))).json()
    except Exception as e:
        return f"Couldn't reach Home Assistant: {e}"

    if not isinstance(states, list):
        return "Home Assistant returned an unexpected response (check the token)."

    def friendly(s):
        return (s.get("attributes", {}).get("friendly_name") or s.get("entity_id", "")).lower()

    # Status query (no on/off intent): report matching entities.
    if action is None:
        matches = [s for s in states if name and name in friendly(s)] if name else []
        if not matches:
            return f"No device matching “{name}”." if name else "What would you like to check or control?"
        return "\n".join(
            f"  {s['attributes'].get('friendly_name', s['entity_id'])}: {s.get('state')}"
            for s in matches[:8])

    # Control: find the best toggleable entity by name + known domain.
    candidates = [s for s in states
                  if name and name in friendly(s)
                  and s.get("entity_id", "").split(".")[0] in _TOGGLEABLE]
    if not candidates:
        return f"Couldn't find a controllable device matching “{name}”."
    entity = candidates[0]["entity_id"]
    domain = entity.split(".")[0]
    service = "turn_on" if action == "on" else "turn_off"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"{url}/api/services/{domain}/{service}",
                headers=_headers(tok), json={"entity_id": entity})
        if r.status_code >= 400:
            return f"Home Assistant rejected the command (HTTP {r.status_code})."
    except Exception as e:
        return f"Command failed: {e}"
    fname = candidates[0]["attributes"].get("friendly_name", entity)
    return f"Turned {action} {fname}."

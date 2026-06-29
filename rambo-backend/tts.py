"""ElevenLabs neural text-to-speech client (best-effort).

synthesize() returns MP3 bytes, or None on any missing config / error so the
caller can fall back to browser speech. Never raises into the voice path.
"""

from __future__ import annotations

import os

import httpx

DEFAULT_VOICE_ID = "jCv6DMvHrCxAiWzQcSEl"
DEFAULT_MODEL = "eleven_turbo_v2_5"

_API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
_SUB_URL = "https://api.elevenlabs.io/v1/user/subscription"


async def get_subscription(api_key: str | None) -> dict | None:
    """Fetch the real ElevenLabs balance. Returns {"used", "limit"} on success,
    or None when there's no key, the key lacks User:Read (401), or any error.
    Best-effort: never raises."""
    if not api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(_SUB_URL, headers={"xi-api-key": api_key})
        if resp.status_code != 200:
            return None
        data = resp.json()
        used = int(data.get("character_count", 0))
        limit = int(data.get("character_limit", 0))
        return {"used": used, "limit": limit}
    except Exception:
        return None


class ElevenLabsTTS:
    def __init__(self, api_key: str | None = None,
                 voice_id: str | None = None,
                 model: str | None = None):
        self.api_key = api_key
        self.voice_id = voice_id
        self.model = model or DEFAULT_MODEL

    @classmethod
    def from_env(cls) -> "ElevenLabsTTS":
        return cls(
            api_key=os.environ.get("ELEVENLABS_API_KEY") or None,
            voice_id=(os.environ.get("ELEVENLABS_VOICE_ID") or DEFAULT_VOICE_ID),
            model=(os.environ.get("ELEVENLABS_MODEL") or DEFAULT_MODEL),
        )

    # Retry transient failures (429 rate-limit, 5xx, network blips) before giving
    # up, so the ElevenLabs voice is used as close to 100% of the time as possible
    # rather than dropping to silence. 4xx auth/quota (401/403) won't recover, so
    # we don't burn retries on those.
    _MAX_ATTEMPTS = 3
    _RETRY_BACKOFF = (0.4, 1.0)  # seconds before attempts 2 and 3

    async def synthesize(self, text: str) -> bytes | None:
        if not self.api_key or not self.voice_id:
            return None
        import asyncio
        from speech_normalize import normalize_for_speech
        text = normalize_for_speech(text)   # "mph" -> "miles per hour", etc.
        url = _API_URL.format(voice_id=self.voice_id)
        headers = {"xi-api-key": self.api_key, "accept": "audio/mpeg"}
        body = {"text": text, "model_id": self.model}
        for attempt in range(self._MAX_ATTEMPTS):
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(url, headers=headers, json=body)
                if resp.status_code == 200 and resp.content:
                    return resp.content
                # Permanent auth/quota errors won't recover — stop retrying.
                if resp.status_code in (401, 403):
                    return None
            except Exception:
                pass  # network blip — fall through to retry
            if attempt < self._MAX_ATTEMPTS - 1:
                await asyncio.sleep(self._RETRY_BACKOFF[attempt])
        return None

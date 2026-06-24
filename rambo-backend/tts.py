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

    async def synthesize(self, text: str) -> bytes | None:
        if not self.api_key or not self.voice_id:
            return None
        url = _API_URL.format(voice_id=self.voice_id)
        headers = {"xi-api-key": self.api_key, "accept": "audio/mpeg"}
        body = {"text": text, "model_id": self.model}
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(url, headers=headers, json=body)
            if resp.status_code != 200:
                return None
            return resp.content
        except Exception:
            return None

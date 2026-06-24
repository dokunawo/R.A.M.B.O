import pytest
import tts as tts_module
from tts import ElevenLabsTTS, DEFAULT_VOICE_ID, DEFAULT_MODEL


class _FakeResponse:
    def __init__(self, status_code, content=b""):
        self.status_code = status_code
        self.content = content


class _FakeClient:
    """Stand-in for httpx.AsyncClient used as an async context manager."""
    last_call = {}

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers=None, json=None):
        _FakeClient.last_call = {"url": url, "headers": headers, "json": json}
        return _FakeResponse(200, b"MP3BYTES")


@pytest.mark.asyncio
async def test_no_api_key_returns_none():
    t = ElevenLabsTTS(api_key=None, voice_id="v")
    assert await t.synthesize("hello") is None


@pytest.mark.asyncio
async def test_no_voice_id_returns_none():
    t = ElevenLabsTTS(api_key="k", voice_id=None)
    assert await t.synthesize("hello") is None


@pytest.mark.asyncio
async def test_success_returns_audio_bytes(monkeypatch):
    monkeypatch.setattr(tts_module.httpx, "AsyncClient", _FakeClient)
    t = ElevenLabsTTS(api_key="k", voice_id="v", model="m")
    out = await t.synthesize("hello")
    assert out == b"MP3BYTES"


@pytest.mark.asyncio
async def test_builds_correct_request(monkeypatch):
    monkeypatch.setattr(tts_module.httpx, "AsyncClient", _FakeClient)
    t = ElevenLabsTTS(api_key="secret", voice_id="voice123", model="model9")
    await t.synthesize("speak this")
    call = _FakeClient.last_call
    assert call["url"] == "https://api.elevenlabs.io/v1/text-to-speech/voice123"
    assert call["headers"]["xi-api-key"] == "secret"
    assert call["headers"]["accept"] == "audio/mpeg"
    assert call["json"] == {"text": "speak this", "model_id": "model9"}


@pytest.mark.asyncio
async def test_non_200_returns_none(monkeypatch):
    class _Bad(_FakeClient):
        async def post(self, url, headers=None, json=None):
            return _FakeResponse(401, b"unauthorized")
    monkeypatch.setattr(tts_module.httpx, "AsyncClient", _Bad)
    t = ElevenLabsTTS(api_key="k", voice_id="v")
    assert await t.synthesize("hi") is None


@pytest.mark.asyncio
async def test_exception_returns_none(monkeypatch):
    class _Boom(_FakeClient):
        async def post(self, url, headers=None, json=None):
            raise RuntimeError("network down")
    monkeypatch.setattr(tts_module.httpx, "AsyncClient", _Boom)
    t = ElevenLabsTTS(api_key="k", voice_id="v")
    assert await t.synthesize("hi") is None


def test_from_env_defaults(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_VOICE_ID", raising=False)
    monkeypatch.delenv("ELEVENLABS_MODEL", raising=False)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "abc")
    t = ElevenLabsTTS.from_env()
    assert t.api_key == "abc"
    assert t.voice_id == DEFAULT_VOICE_ID == "jCv6DMvHrCxAiWzQcSEl"
    assert t.model == DEFAULT_MODEL == "eleven_turbo_v2_5"


def test_from_env_overrides(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "abc")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "myvoice")
    monkeypatch.setenv("ELEVENLABS_MODEL", "mymodel")
    t = ElevenLabsTTS.from_env()
    assert t.voice_id == "myvoice"
    assert t.model == "mymodel"


# --- get_subscription -----------------------------------------------------

class _SubResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
    def json(self):
        return self._payload


class _SubClient:
    """Async-context httpx stand-in exposing get()."""
    status = 200
    payload = {"character_count": 8420, "character_limit": 10000}
    def __init__(self, *a, **k): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *e): return False
    async def get(self, url, headers=None):
        _SubClient.last = {"url": url, "headers": headers}
        return _SubResponse(_SubClient.status, _SubClient.payload)


@pytest.mark.asyncio
async def test_subscription_none_without_key():
    assert await tts_module.get_subscription(None) is None


@pytest.mark.asyncio
async def test_subscription_success(monkeypatch):
    _SubClient.status = 200
    _SubClient.payload = {"character_count": 8420, "character_limit": 10000}
    monkeypatch.setattr(tts_module.httpx, "AsyncClient", _SubClient)
    out = await tts_module.get_subscription("key")
    assert out == {"used": 8420, "limit": 10000}
    assert _SubClient.last["url"] == "https://api.elevenlabs.io/v1/user/subscription"
    assert _SubClient.last["headers"]["xi-api-key"] == "key"


@pytest.mark.asyncio
async def test_subscription_401_returns_none(monkeypatch):
    _SubClient.status = 401
    monkeypatch.setattr(tts_module.httpx, "AsyncClient", _SubClient)
    assert await tts_module.get_subscription("key") is None


@pytest.mark.asyncio
async def test_subscription_exception_returns_none(monkeypatch):
    class _Boom(_SubClient):
        async def get(self, url, headers=None):
            raise RuntimeError("down")
    monkeypatch.setattr(tts_module.httpx, "AsyncClient", _Boom)
    assert await tts_module.get_subscription("key") is None

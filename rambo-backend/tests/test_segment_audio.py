import base64
import pytest
from orchestrator.orchestrator import Orchestrator


class _CapturingWS:
    def __init__(self):
        self.messages = []

    async def broadcast_json(self, payload):
        self.messages.append(payload)


class _StubTTS:
    def __init__(self, data):
        self.data = data

    async def synthesize(self, text):
        return self.data


@pytest.mark.asyncio
async def test_emit_segment_includes_audio_when_tts_present():
    o = Orchestrator.__new__(Orchestrator)
    o.ws = _CapturingWS()
    o.tts = _StubTTS(b"AUDIO")
    await o._emit_segment("Hello sir.", "turn1", 0, True, 0.0)
    msg = o.ws.messages[-1]
    assert msg["t"] == "speak_segment"
    assert msg["text"] == "Hello sir."
    assert msg["audio"] == base64.b64encode(b"AUDIO").decode("ascii")


@pytest.mark.asyncio
async def test_emit_segment_no_audio_when_tts_none():
    o = Orchestrator.__new__(Orchestrator)
    o.ws = _CapturingWS()
    o.tts = None
    await o._emit_segment("Hello sir.", "turn1", 0, True, 0.0)
    msg = o.ws.messages[-1]
    assert "audio" not in msg


@pytest.mark.asyncio
async def test_emit_segment_no_audio_when_attr_missing():
    o = Orchestrator.__new__(Orchestrator)
    o.ws = _CapturingWS()
    # no o.tts set at all — must not raise (getattr fallback)
    await o._emit_segment("Hi.", "turn1", 0, False, 0.0)
    assert o.ws.messages[-1]["t"] == "speak_segment"


@pytest.mark.asyncio
async def test_segment_audio_swallows_synth_error():
    class _Boom:
        async def synthesize(self, text):
            raise RuntimeError("boom")
    o = Orchestrator.__new__(Orchestrator)
    o.tts = _Boom()
    assert await o._segment_audio("x") is None


# --- ElevenLabs character-usage recording ---------------------------------

class _RecordingRepo:
    def __init__(self):
        self.records = []
    async def record(self, characters, model=""):
        self.records.append((characters, model))


@pytest.mark.asyncio
async def test_segment_audio_records_characters_on_success():
    o = Orchestrator.__new__(Orchestrator)
    o.tts = _StubTTS(b"AUDIO")
    o.tts.model = "eleven_turbo_v2_5"
    repo = _RecordingRepo()
    o.tts_usage_repo = repo
    out = await o._segment_audio("Hello sir.")
    assert out is not None
    assert repo.records == [(len("Hello sir."), "eleven_turbo_v2_5")]


@pytest.mark.asyncio
async def test_segment_audio_no_record_when_synth_none():
    o = Orchestrator.__new__(Orchestrator)
    o.tts = _StubTTS(None)
    repo = _RecordingRepo()
    o.tts_usage_repo = repo
    out = await o._segment_audio("Hello sir.")
    assert out is None
    assert repo.records == []


@pytest.mark.asyncio
async def test_segment_audio_no_repo_does_not_raise():
    o = Orchestrator.__new__(Orchestrator)
    o.tts = _StubTTS(b"AUDIO")
    # no tts_usage_repo attribute at all
    out = await o._segment_audio("Hi.")
    assert out is not None

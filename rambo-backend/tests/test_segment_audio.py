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

# ElevenLabs Neural Voice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Speak R.A.M.B.O's responses with an ElevenLabs neural voice (server-side synthesis streamed over the existing WebSocket), with the orb pulsing to that voice, falling back to the browser voice whenever ElevenLabs is unavailable.

**Architecture:** A new best-effort `ElevenLabsTTS` backend client synthesizes each sentence segment; `_speak()`/`_emit_segment()` attach base64 audio to the existing `speak_segment` WS message; the frontend plays that audio through Web Audio routed via an AnalyserNode that drives the orb, falling back to `speechSynthesis` when no audio is present.

**Tech Stack:** Python, FastAPI, httpx (already a dependency), aiosqlite-style env config, React, Web Audio API, pytest + pytest-asyncio.

## Global Constraints

- TTS is best-effort: missing API key, missing voice id, non-200, or any exception ⇒ `synthesize` returns `None` and the system falls back to browser `speechSynthesis`. A turn must never break because TTS failed.
- The ElevenLabs API key is read only from the environment server-side; it is never sent to the browser.
- Env vars: `ELEVENLABS_API_KEY` (secret, no default), `ELEVENLABS_VOICE_ID` (default `jCv6DMvHrCxAiWzQcSEl`), `ELEVENLABS_MODEL` (default `eleven_turbo_v2_5`).
- ElevenLabs request: `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}`, headers `xi-api-key: <key>` and `accept: audio/mpeg`, JSON body `{"text": <text>, "model_id": <model>}`.
- Reading the injected TTS client uses `getattr(self, "tts", None)` so orchestrators built via `Orchestrator.__new__` (the streaming tests) keep working.
- Additive only: with no API key, behavior is identical to today and the existing suite (219 tests) stays green.
- Tests use `pytest`, `pytest_asyncio`, `@pytest.mark.asyncio`, `monkeypatch`. Run from `rambo-backend/`. All work on branch `feature/elevenlabs-voice`.

---

### Task 1: `ElevenLabsTTS` client

**Files:**
- Create: `rambo-backend/tts.py`
- Test: `rambo-backend/tests/test_tts.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `ElevenLabsTTS(api_key: str | None = None, voice_id: str | None = None, model: str | None = None)` with attributes `api_key`, `voice_id`, `model`.
  - `async synthesize(self, text: str) -> bytes | None`
  - classmethod `from_env() -> "ElevenLabsTTS"` reading the three env vars with the defaults from Global Constraints.
  - module constants `DEFAULT_VOICE_ID = "jCv6DMvHrCxAiWzQcSEl"`, `DEFAULT_MODEL = "eleven_turbo_v2_5"`.

- [ ] **Step 1: Write the failing tests**

Create `rambo-backend/tests/test_tts.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd rambo-backend && python -m pytest tests/test_tts.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tts'`

- [ ] **Step 3: Implement `tts.py`**

Create `rambo-backend/tts.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd rambo-backend && python -m pytest tests/test_tts.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/tts.py rambo-backend/tests/test_tts.py
git commit -m "feat: add ElevenLabsTTS best-effort client"
```

---

### Task 2: Orchestrator emits segment audio

**Files:**
- Modify: `rambo-backend/orchestrator/orchestrator.py` (`__init__`, new `set_tts`, new `_segment_audio`, `_emit_segment`)
- Test: `rambo-backend/tests/test_segment_audio.py` (create)

**Interfaces:**
- Consumes: `ElevenLabsTTS.synthesize` (Task 1) — any object with `async synthesize(text) -> bytes | None` works (tests use a stub).
- Produces: `Orchestrator.set_tts(tts)`; `self.tts` attribute (default `None`); `_emit_segment` now broadcasts an optional `"audio"` (base64 str) field on the `speak_segment` message.

- [ ] **Step 1: Write the failing test**

Create `rambo-backend/tests/test_segment_audio.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd rambo-backend && python -m pytest tests/test_segment_audio.py -v`
Expected: FAIL — `AttributeError: 'Orchestrator' object has no attribute '_segment_audio'` (and the audio-field assertions fail).

- [ ] **Step 3: Add the attribute, setter, helper, and audio field**

In `rambo-backend/orchestrator/orchestrator.py` `__init__`, beside `self.dispatch_repo = None`, add:

```python
        self.tts = None
```

Add the setter next to `set_dispatch_repo`:

```python
    def set_tts(self, tts):
        """Give the orchestrator a best-effort TTS client (or None)."""
        self.tts = tts
```

Add the helper (near the other best-effort helpers). Put the `import base64` at the top of the method to avoid a module-level import churn:

```python
    async def _segment_audio(self, text: str) -> str | None:
        """Synthesize a spoken segment to base64 MP3, best-effort. None on
        missing client, empty result, or any error."""
        tts = getattr(self, "tts", None)
        if not tts:
            return None
        try:
            data = await tts.synthesize(text)
            if not data:
                return None
            import base64
            return base64.b64encode(data).decode("ascii")
        except Exception:
            return None
```

Now update `_emit_segment`. The current method body is:

```python
    async def _emit_segment(self, text: str, base_turn_id: str, seq: int, is_final: bool, t0: float):
        segment_id = f"{base_turn_id}::{seq}"
        await self.ws.broadcast_json({
            "t": "speak_segment",
            "turn_id": segment_id,
            "base_turn_id": base_turn_id,
            "seq": seq,
            "text": text,
            "is_final": is_final,
        })
        elapsed = time.monotonic() - t0
        print(f"[stream] speak_segment base={base_turn_id} seq={seq} "
              f"chars={len(text)} t_since_start={elapsed:.2f}s final={is_final}")
```

Replace it with a version that builds the payload, conditionally adds `audio`:

```python
    async def _emit_segment(self, text: str, base_turn_id: str, seq: int, is_final: bool, t0: float):
        segment_id = f"{base_turn_id}::{seq}"
        payload = {
            "t": "speak_segment",
            "turn_id": segment_id,
            "base_turn_id": base_turn_id,
            "seq": seq,
            "text": text,
            "is_final": is_final,
        }
        audio = await self._segment_audio(text)
        if audio:
            payload["audio"] = audio
        await self.ws.broadcast_json(payload)
        elapsed = time.monotonic() - t0
        print(f"[stream] speak_segment base={base_turn_id} seq={seq} "
              f"chars={len(text)} t_since_start={elapsed:.2f}s final={is_final}")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd rambo-backend && python -m pytest tests/test_segment_audio.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Run the streaming suite to confirm no regression**

Run: `cd rambo-backend && python -m pytest tests/test_streaming.py -v`
Expected: PASS (all — `tts` is absent on `__new__`-built orchestrators and `_segment_audio` returns None via getattr).

- [ ] **Step 6: Commit**

```bash
git add rambo-backend/orchestrator/orchestrator.py rambo-backend/tests/test_segment_audio.py
git commit -m "feat: attach ElevenLabs segment audio to speak_segment (best-effort)"
```

---

### Task 3: Wire TTS into app startup

**Files:**
- Modify: `rambo-backend/main.py`
- Test: none (verified by import + full suite)

**Interfaces:**
- Consumes: `ElevenLabsTTS.from_env` (Task 1), `Orchestrator.set_tts` (Task 2).
- Produces: a live TTS client attached to the orchestrator when `ELEVENLABS_API_KEY` is set.

- [ ] **Step 1: Add the import and startup wiring**

In `rambo-backend/main.py`, near the other imports (e.g. after `from dispatch_repo import DispatchRepo`) add:

```python
import os
from tts import ElevenLabsTTS
```

(If `import os` is already present at the top, do not duplicate it.)

After the existing `_init_dispatch_db` startup hook, add:

```python
@app.on_event("startup")
async def _init_tts():
    if os.environ.get("ELEVENLABS_API_KEY"):
        rambo.set_tts(ElevenLabsTTS.from_env())
```

- [ ] **Step 2: Verify the app imports cleanly**

Run: `cd rambo-backend && python -c "import main; print('ok')"`
Expected: prints `ok` with no import error.

- [ ] **Step 3: Run the full suite**

Run: `cd rambo-backend && python -m pytest -q`
Expected: PASS (all prior + existing tests green).

- [ ] **Step 4: Commit**

```bash
git add rambo-backend/main.py
git commit -m "feat: initialize ElevenLabs TTS on startup when API key present"
```

---

### Task 4: Frontend plays segment audio + drives the orb

**Files:**
- Modify: `rambo-frontend/src/components/useVoiceReactivity.js`
- Test: verified via preview tools (Web Audio playback is not unit-testable here)

**Interfaces:**
- Consumes: the `speak_segment` WS message which now may carry `audio` (base64 MP3 string) plus existing `text`, `is_final`, `base_turn_id`, `seq`.
- Produces: no exported signature change; internal `speakSegment` now takes the segment object and plays audio when present.

- [ ] **Step 1: Add a Web Audio segment player**

Near the top of `useVoiceReactivity.js` (module scope, beside the existing `speak`/`speakSegment` helpers), add a shared audio context and an analyser-driven player. The analyser writes into a module-level `ttsLevelRef` object the hook will read:

```javascript
// Shared context for TTS playback so the orb can react to RAMBO's own voice.
let ttsCtx = null;
let ttsAnalyser = null;
export const ttsLevel = { value: 0 };

function ensureTtsCtx() {
  if (typeof window === "undefined") return null;
  const AC = window.AudioContext || window.webkitAudioContext;
  if (!AC) return null;
  if (!ttsCtx) {
    ttsCtx = new AC();
    ttsAnalyser = ttsCtx.createAnalyser();
    ttsAnalyser.fftSize = 256;
    ttsAnalyser.connect(ttsCtx.destination);
  }
  return ttsCtx;
}

function base64ToArrayBuffer(b64) {
  const bin = atob(b64);
  const len = bin.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) bytes[i] = bin.charCodeAt(i);
  return bytes.buffer;
}

// Resolves when playback ends. Updates ttsLevel.value with the RMS of the
// playing audio so the orb can pulse to RAMBO's voice.
function playAudioSegment(b64) {
  return new Promise((resolve) => {
    const ctx = ensureTtsCtx();
    if (!ctx) { resolve(false); return; }
    let settled = false;
    const done = (ok) => { if (!settled) { settled = true; ttsLevel.value = 0; resolve(ok); } };
    try {
      if (ctx.state === "suspended") ctx.resume().catch(() => {});
      ctx.decodeAudioData(base64ToArrayBuffer(b64), (buf) => {
        const src = ctx.createBufferSource();
        src.buffer = buf;
        src.connect(ttsAnalyser);
        const data = new Uint8Array(ttsAnalyser.frequencyBinCount);
        let raf;
        const sample = () => {
          ttsAnalyser.getByteTimeDomainData(data);
          let sum = 0;
          for (let i = 0; i < data.length; i++) {
            const v = (data[i] - 128) / 128;
            sum += v * v;
          }
          ttsLevel.value = Math.sqrt(sum / data.length);
          raf = requestAnimationFrame(sample);
        };
        src.onended = () => { cancelAnimationFrame(raf); done(true); };
        src.start();
        sample();
      }, () => done(false));
    } catch {
      done(false);
    }
  });
}
```

- [ ] **Step 2: Make `speakSegment` prefer audio, fall back to speech**

Replace the existing module-level `speakSegment(text)` so it accepts the segment object. The current function:

```javascript
function speakSegment(text) {
  return new Promise((resolve) => {
    const synth = window.speechSynthesis;
    if (!synth) { resolve(); return; }
    const utter = new SpeechSynthesisUtterance(text);
    const preferred = getPreferredVoice();
    if (preferred) utter.voice = preferred;
    // ... existing onend wiring ...
  });
}
```

becomes:

```javascript
function speakSegment(seg) {
  const text = typeof seg === "string" ? seg : seg.text;
  const audio = typeof seg === "string" ? null : seg.audio;
  if (audio) {
    return playAudioSegment(audio).then((ok) => {
      if (ok) return;
      return speakViaSynth(text);   // fallback if decode/playback failed
    });
  }
  return speakViaSynth(text);
}

function speakViaSynth(text) {
  return new Promise((resolve) => {
    const synth = window.speechSynthesis;
    if (!synth) { resolve(); return; }
    const utter = new SpeechSynthesisUtterance(text);
    const preferred = getPreferredVoice();
    if (preferred) utter.voice = preferred;
    utter.onend = () => resolve();
    utter.onerror = () => resolve();
    synth.speak(utter);
  });
}
```

(Preserve any rate/pitch/volume settings the original `speakSegment` set on `utter` by carrying them into `speakViaSynth`.)

- [ ] **Step 3: Pass the whole segment object through `pumpQueue`**

In `pumpQueue`, the current call is `await speakSegment(seg.text);`. Change it to:

```javascript
    await speakSegment(seg);
```

(`seg` is the queued `speak_segment` message object, which carries `text` and optional `audio`.)

- [ ] **Step 4: Feed the TTS level into the orb during SPEAKING**

In the `tick` animation loop that updates `levelRef.current` from the mic analyser, prefer the TTS level while a segment is playing. Find the line that assigns the smoothed mic level to `levelRef.current` and gate it:

```javascript
    // While RAMBO is speaking, drive the orb from its own voice instead of mic.
    if (ttsLevel.value > 0) {
      levelRef.current = levelRef.current + 0.3 * (ttsLevel.value - levelRef.current);
    } else {
      // existing mic-driven smoothing
      const alpha = rms > prev ? SMOOTH_UP : SMOOTH_DOWN;
      levelRef.current = prev + alpha * (rms - prev);
    }
```

(Keep the existing mic computation above it intact; only the assignment to `levelRef.current` is gated.)

- [ ] **Step 5: Verify in the browser (preview tools)**

Start the app, trigger a spoken response, and confirm with the preview tools:
- With `ELEVENLABS_API_KEY` set: the ElevenLabs voice plays (not the robotic browser voice) and the orb pulses while RAMBO speaks. Check the console/network for the `speak_segment` messages carrying `audio` and no playback errors.
- Temporarily unset the key (or simulate no `audio`): confirm it falls back to the browser voice and still works.

- [ ] **Step 6: Commit**

```bash
git add rambo-frontend/src/components/useVoiceReactivity.js
git commit -m "feat: play ElevenLabs segment audio and pulse orb to RAMBO voice"
```

---

### Task 5: Document the env vars

**Files:**
- Modify or create: `rambo-backend/.env.example`

**Interfaces:**
- Consumes: nothing.
- Produces: documented `ELEVENLABS_*` vars for operators.

- [ ] **Step 1: Add the vars to `.env.example`**

If `rambo-backend/.env.example` exists, append; otherwise create it with at least these lines (do NOT include real secrets):

```env
# ElevenLabs neural voice (optional). Without ELEVENLABS_API_KEY, R.A.M.B.O
# falls back to the browser's built-in speech voice.
ELEVENLABS_API_KEY=
# Voice to speak with (defaults to this if unset).
ELEVENLABS_VOICE_ID=jCv6DMvHrCxAiWzQcSEl
# TTS model (low-latency default).
ELEVENLABS_MODEL=eleven_turbo_v2_5
```

- [ ] **Step 2: Verify it is not ignored in a way that hides the example**

Run: `cd rambo-backend && git check-ignore -v .env.example || echo "tracked: ok"`
Expected: prints `tracked: ok` (the example must be committable; only the real `.env` is ignored).

- [ ] **Step 3: Commit**

```bash
git add rambo-backend/.env.example
git commit -m "docs: document ELEVENLABS_* env vars in .env.example"
```

---

## Self-Review

**Spec coverage:**
- `tts.py` client, env config, best-effort None contract, correct request shape → Task 1. ✓
- Orchestrator `set_tts`, `_segment_audio`, audio on `speak_segment`, getattr resilience → Task 2. ✓
- main.py startup wiring (key-gated) → Task 3. ✓
- Frontend audio playback, AnalyserNode → orb, speechSynthesis fallback, pumpQueue passes object → Task 4. ✓
- `.env.example` / env docs → Task 5. ✓
- Error-handling table (no key / no voice / non-200 / decode fail) → Task 1 (backend Nones) + Task 4 (frontend fallback). ✓
- Orb pulses to RAMBO voice during SPEAKING → Task 4 Step 4. ✓
- Additive / 219 tests stay green → Task 2 Step 5 + Task 3 Step 3. ✓

**Placeholder scan:** No TBD/TODO; every code step shows full code. The one prose instruction (carry rate/pitch into `speakViaSynth`) references concrete existing settings, not a vague directive. ✓

**Type consistency:** `synthesize(text) -> bytes | None`, `from_env()`, `set_tts(tts)`, `_segment_audio(text) -> str | None`, `speakSegment(seg)`, `playAudioSegment(b64) -> Promise<bool>`, `ttsLevel.value` — names consistent across Tasks 1–4. ✓

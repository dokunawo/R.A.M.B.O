# Design: ElevenLabs Neural Voice for R.A.M.B.O

**Date:** 2026-06-24
**Status:** Approved (design), pending implementation plan

## Background

R.A.M.B.O already has a complete voice loop: microphone speech-to-text
(`webkitSpeechRecognition`), a wake word ("Rambo"), a conversation loop with
follow-ups, a reactive orb, and spoken responses. But responses are spoken with
the **browser's built-in `window.speechSynthesis`** (`useVoiceReactivity.js`),
which sounds robotic. The goal is to replace that with **ElevenLabs neural TTS**
for a cinematic, natural voice — while preserving the existing loop and degrading
gracefully when ElevenLabs is unavailable.

Inspiration: the ethanplusai/jarvis project, which uses a cloud TTS (Fish Audio)
for its voice. R.A.M.B.O will use ElevenLabs instead.

## Goals

- Speak responses with an ElevenLabs neural voice (configurable voice).
- Make the orb pulse to R.A.M.B.O's **own voice** while speaking (today it only
  reacts to mic input).
- Degrade gracefully: with no API key, no voice id, or any error, fall back to
  today's `speechSynthesis`. A turn must never break because TTS failed.
- Keep the API key server-side (never shipped to the browser).

## Non-Goals

- No change to speech-to-text, the wake word, or the conversation loop.
- No streaming/partial-audio from ElevenLabs (synthesize per sentence-segment,
  which already matches the existing segment queue).
- No voice-cloning workflow — the user supplies a ready voice id.

## Approach

Chosen: **server-side synthesis, audio bundled into the existing
`speak_segment` WebSocket message.** The backend synthesizes each sentence
segment and attaches the audio; the frontend plays it through Web Audio (which
also drives the orb). Rejected alternatives: browser calling ElevenLabs directly
(exposes the key), and a separate `/tts` HTTP endpoint (extra round-trip per
sentence and a second channel to keep in sync with the WS stream).

## Components

### Backend — new `rambo-backend/tts.py`

A small, self-contained TTS client:

```python
class ElevenLabsTTS:
    def __init__(self, api_key: str | None = None,
                 voice_id: str | None = None,
                 model: str | None = None): ...
    async def synthesize(self, text: str) -> bytes | None: ...
```

- Config via environment (with module-level defaults):
  - `ELEVENLABS_API_KEY` — required for synthesis; absent ⇒ `synthesize` returns
    `None`. **Secret — never committed.**
  - `ELEVENLABS_VOICE_ID` — default `jCv6DMvHrCxAiWzQcSEl` (the user's voice).
  - `ELEVENLABS_MODEL` — default `eleven_turbo_v2_5` (low latency).
- `synthesize(text)`:
  - Returns `None` immediately if `api_key` or `voice_id` is missing.
  - Otherwise POSTs to
    `https://api.elevenlabs.io/v1/text-to-speech/{voice_id}` with header
    `xi-api-key: <key>`, `accept: audio/mpeg`, JSON body
    `{"text": ..., "model_id": <model>}`, via async `httpx` (already a
    dependency).
  - Returns MP3 bytes on HTTP 200; returns `None` on any non-200 or exception.
    **Best-effort: never raises.**
- A `from_env()` constructor/factory builds an instance from the environment.

### Backend — orchestrator wiring

- `Orchestrator.__init__` gains `self.tts = None`.
- `set_tts(tts)` setter (mirrors `set_dispatch_repo`).
- `main.py` startup builds `ElevenLabsTTS.from_env()` and calls
  `rambo.set_tts(tts)` only when an API key is present; otherwise leaves `tts`
  as `None` (today's behavior). Mirrors the usage/factory/dispatch wiring.

### Backend — `_speak()` in `orchestrator/orchestrator.py`

The `_speak` streaming loop already emits each finished sentence as a
`speak_segment` message via `_emit_segment(...)`. Change:

- A best-effort helper `_segment_audio(text) -> str | None`: if `self.tts` is
  set, `await self.tts.synthesize(text)`, base64-encode the bytes, return the
  string; on `None`/exception return `None`.
- `_emit_segment` includes an `audio` field (base64 MP3 string) when available;
  the message is otherwise unchanged, so a text-only segment (no TTS) behaves
  exactly as today.
- Reading `self.tts` via `getattr(self, "tts", None)` keeps the streaming tests
  that build the orchestrator via `__new__` working (same lesson as the dispatch
  work).

### Frontend — `useVoiceReactivity.js` + Web Audio playback

- The module-level `speakSegment(text)` becomes `speakSegment(msg)`:
  - If `msg.audio` is present: decode base64 → `ArrayBuffer` →
    `audioCtx.decodeAudioData` → `AudioBufferSourceNode` → **AnalyserNode** →
    destination. Resolve the promise on the source's `ended` event.
  - Else: fall back to `speechSynthesis(msg.text)` exactly as today.
- The `AnalyserNode` writes RMS level into the **same `levelRef`** the orb reads,
  but only while a TTS segment is playing — so the orb pulses to R.A.M.B.O's
  voice during SPEAKING and returns to mic-driven levels during LISTENING.
- `pumpQueue` passes the whole segment object (which already carries `text`) to
  `speakSegment` instead of just the text.
- A single shared `AudioContext` is reused (created lazily on first user gesture,
  consistent with `audioEngine.js`).

### Config & docs

- `.env.example` documents `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` (default
  shown), `ELEVENLABS_MODEL`.
- `env_setup.py` is updated if it enumerates known/required vars.

## Data Flow

```
_speak() streams sentence segment
   └─ if self.tts: synthesize → base64
   └─ emit speak_segment { turn_id, seq, text, is_final, audio? }
        └─ WS → frontend handleSpeakSegment → queue → pumpQueue
             └─ speakSegment(msg)
                  ├─ msg.audio → Web Audio buffer → AnalyserNode → speakers
                  │     └─ analyser RMS → levelRef → orb pulses to RAMBO voice
                  └─ no audio → speechSynthesis(msg.text)  (fallback)
```

## Error Handling

Every failure path falls back to `speechSynthesis`, never breaks a turn:

| Failure | Result |
|---------|--------|
| No `ELEVENLABS_API_KEY` | `tts` is `None`; segments emit text-only; browser TTS |
| No `ELEVENLABS_VOICE_ID` | `synthesize` returns `None`; browser TTS |
| ElevenLabs non-200 / network error | `synthesize` returns `None`; browser TTS |
| Base64 decode / `decodeAudioData` fails in browser | catch → `speechSynthesis(msg.text)` |

## Testing

**Backend (pytest):**
- `tts.py`: `synthesize` returns `None` when api_key unset; returns `None` when
  voice_id unset; on a mocked httpx 200 returns the body bytes; on a mocked
  non-200 returns `None`; on a mocked httpx exception returns `None`; builds the
  correct URL, `xi-api-key` header, and `model_id` body (assert against the
  mocked request).
- `from_env()` honors `ELEVENLABS_VOICE_ID` / `ELEVENLABS_MODEL` overrides and
  the `jCv6DMvHrCxAiWzQcSEl` / `eleven_turbo_v2_5` defaults.
- `_speak`/`_emit_segment`: with a stub `tts` returning bytes, the emitted
  `speak_segment` includes a base64 `audio` field; with `tts = None`, no `audio`
  field is present (and existing streaming tests stay green).

**Frontend:** verified with the preview tools — trigger a response, confirm
ElevenLabs audio plays and the orb reacts while speaking; with no key, confirm
the browser-voice fallback still works. Web Audio playback is not meaningfully
unit-testable.

## Risk / Rollback

- Fully additive and gated on `tts` being set. With no API key the system
  behaves exactly as today (219 tests stay green).
- The voice id is not a secret and is safe to default in config; the API key is
  read only from the environment and never sent to the browser.
- Per-segment synthesis adds latency to each spoken sentence; mitigated by the
  low-latency `eleven_turbo_v2_5` model and short segments. If latency is a
  problem, the model is env-overridable.

"""
Generates the voice/streaming loop AUTO block by inspecting the pipeline components.
"""

from __future__ import annotations

import os
from pathlib import Path


_BACKEND = Path(__file__).resolve().parent.parent.parent
_FRONTEND_COMPONENTS = _BACKEND.parent / "rambo-frontend" / "src" / "components"


def generate() -> str:
    components = []

    # Server-side: orchestrator._speak()
    orch_path = _BACKEND / "orchestrator" / "orchestrator.py"
    if orch_path.exists():
        src = orch_path.read_text(encoding="utf-8")
        streaming = "messages.stream" in src
        sentence_split = "_split_sentence" in src
        components.append({
            "layer": "LLM streaming",
            "location": "`orchestrator/orchestrator.py:_speak()`",
            "detail": f"{'Streaming' if streaming else 'Blocking'} Anthropic call"
                      + (", per-sentence splitting" if sentence_split else ""),
        })

    # Server-side: WebSocket broadcast
    ws_path = _BACKEND / "websocket" / "manager.py"
    if ws_path.exists():
        src = ws_path.read_text(encoding="utf-8")
        has_broadcast_json = "broadcast_json" in src
        components.append({
            "layer": "Transport",
            "location": "`websocket/manager.py`",
            "detail": f"WebSocket at `/ws/activity`"
                      + (" with `broadcast_json`" if has_broadcast_json else ""),
        })

    # Client-side: STT
    voice_hook = _FRONTEND_COMPONENTS / "useVoiceReactivity.js"
    if voice_hook.exists():
        src = voice_hook.read_text(encoding="utf-8")
        has_stt = "SpeechRecognition" in src
        has_tts = "speechSynthesis" in src
        has_segment_queue = "speakSegment" in src
        components.append({
            "layer": "STT",
            "location": "`useVoiceReactivity.js`",
            "detail": "Browser-native `SpeechRecognition`" if has_stt else "not detected",
        })
        components.append({
            "layer": "TTS",
            "location": "`useVoiceReactivity.js`",
            "detail": ("Browser-native `speechSynthesis`"
                       + (", segment queue" if has_segment_queue else "")),
        })

    # Client-side: VAD
    voice_controls = _FRONTEND_COMPONENTS / "VoiceControls.jsx"
    if voice_controls.exists():
        components.append({
            "layer": "VAD",
            "location": "`useVoiceReactivity.js`",
            "detail": "Silence timer (1000ms) triggers final transcript",
        })

    if not components:
        return "_Voice loop not detected._"

    lines = ["| Layer | Location | Detail |", "| --- | --- | --- |"]
    for c in components:
        lines.append(f"| {c['layer']} | {c['location']} | {c['detail']} |")

    return "\n".join(lines)

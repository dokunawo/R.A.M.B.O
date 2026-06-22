// VoiceControls.jsx — Shared mic toggle + volume toggle for all pages.
import React, { useState, useEffect, useRef } from "react";
import { useVoiceReactivity, CONV_STATES } from "./useVoiceReactivity";
import { isMuted, setMuted, resumeAudio } from "./audioEngine";
import "./VoiceControls.css";

export function usePageVoice() {
  const [voiceText, setVoiceText] = useState("");
  const voiceSetStateRef = useRef(null);
  const speakRef = useRef(null);

  const handleFinalTranscript = (text) => {
    setVoiceText(text);
    setTimeout(() => {
      if (voiceSetStateRef.current) voiceSetStateRef.current(CONV_STATES.PROCESSING);
    }, 800);
  };

  const voice = useVoiceReactivity({
    onTranscript: setVoiceText,
    onFinalTranscript: handleFinalTranscript,
  });

  voiceSetStateRef.current = voice.setState;
  speakRef.current = voice.speakResponse;

  // Auto-start mic on mount
  const started = useRef(false);
  useEffect(() => {
    if (!started.current) {
      started.current = true;
      setTimeout(() => voice.startMic(), 1200);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { ...voice, voiceText, setVoiceText, speakRef };
}

export function VoiceControls({ micActive, toggleMic, convState }) {
  const [muted, setMutedState] = useState(isMuted());
  const toggleVolume = () => {
    resumeAudio();
    setMutedState(setMuted(!muted));
  };

  return (
    <div className="voice-controls">
      <button className="vc-btn" type="button" onClick={toggleVolume}
        title={muted ? "Sound off — click to enable" : "Sound on"}>
        {muted ? "🔇" : "🔊"}
      </button>
      <button className="vc-btn" type="button" onClick={toggleMic}
        title={micActive ? 'Mic active — say "Rambo" to command' : 'Enable mic'}>
        {micActive ? "🎙️" : "🎤"}
        {micActive && <span className="vc-state">{convState.toUpperCase()}</span>}
      </button>
    </div>
  );
}

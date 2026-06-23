import React, { useState, useEffect, useRef, useCallback } from "react";
import { useVoiceReactivity, CONV_STATES } from "./useVoiceReactivity";
import { isMuted, setMuted, resumeAudio } from "./audioEngine";
import "./VoiceControls.css";

const API = "http://localhost:8000";

export function usePageVoice() {
  const [voiceText, setVoiceText] = useState("");
  const [commandLog, setCommandLog] = useState([]);
  const [busy, setBusy] = useState(false);
  const voiceSetStateRef = useRef(null);
  const speakRef = useRef(null);

  const executeCommand = useCallback(async (text) => {
    if (!text.trim() || busy) return;
    setBusy(true);
    const entry = { id: Date.now(), time: new Date().toLocaleTimeString(), command: text, response: null, status: "processing" };
    setCommandLog(prev => [entry, ...prev].slice(0, 50));

    try {
      const res = await fetch(`${API}/rambo/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal: text }),
      });
      const data = await res.json().catch(() => ({}));
      const responseText = data.response || "(no response)";
      setCommandLog(prev => prev.map(e =>
        e.id === entry.id ? { ...e, response: responseText, status: "complete" } : e
      ));
      if (speakRef.current) speakRef.current(responseText, true);
    } catch {
      setCommandLog(prev => prev.map(e =>
        e.id === entry.id ? { ...e, response: "Request failed — backend offline", status: "error" } : e
      ));
    } finally {
      setBusy(false);
    }
  }, [busy]);

  const handleFinalTranscript = useCallback((text) => {
    setVoiceText(text);
    setTimeout(() => {
      executeCommand(text);
      if (voiceSetStateRef.current) voiceSetStateRef.current(CONV_STATES.PROCESSING);
    }, 800);
  }, [executeCommand]);

  const voice = useVoiceReactivity({
    onTranscript: setVoiceText,
    onFinalTranscript: handleFinalTranscript,
  });

  voiceSetStateRef.current = voice.setState;
  speakRef.current = voice.speakResponse;

  const started = useRef(false);
  useEffect(() => {
    if (!started.current) {
      started.current = true;
      setTimeout(() => voice.startMic(), 1200);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { ...voice, voiceText, setVoiceText, speakRef, commandLog, executeCommand, busy };
}

export function VoiceControls({ micActive, toggleMic, convState }) {
  const [muted, setMutedState] = useState(isMuted());
  const toggleVolume = () => {
    resumeAudio();
    setMutedState(setMuted(!muted));
  };

  const isListening = convState === CONV_STATES.LISTENING;
  const isProcessing = convState === CONV_STATES.PROCESSING;
  const isActive = micActive && (isListening || isProcessing);

  return (
    <div className="vc-bar">
      <div className="vc-bar-center">
        <button
          className={`vc-mic-primary${isActive ? " vc-mic-active" : ""}${isProcessing ? " vc-mic-processing" : ""}`}
          type="button"
          onClick={toggleMic}
          title={micActive ? 'Mic active — say "Rambo" to command' : "Enable mic"}
        >
          {isActive ? (
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <rect x="3" y="3" width="10" height="10" rx="1.5" fill="white"/>
            </svg>
          ) : (
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="9" y="2" width="6" height="11" rx="3"/>
              <path d="M5 10a7 7 0 0 0 14 0"/>
              <line x1="12" y1="19" x2="12" y2="22"/>
            </svg>
          )}
        </button>
        <button className="vc-vol-secondary" type="button" onClick={toggleVolume}
          title={muted ? "Sound off — click to enable" : "Sound on"}>
          {muted ? "🔇" : "🔊"}
        </button>
      </div>
      {!isActive && (
        <span className="vc-hint">TAP OR SAY 'RAMBO'</span>
      )}
    </div>
  );
}

export function CommandLog({ commandLog, agentColor }) {
  if (commandLog.length === 0) return null;
  return (
    <div className="cmd-log">
      <div className="cmd-log-header" style={{ borderColor: agentColor || "#e8b15a" }}>
        <span className="cmd-log-icon">◆</span> COMMAND LOG
      </div>
      <div className="cmd-log-entries">
        {commandLog.map(entry => (
          <div key={entry.id} className={`cmd-log-entry cmd-log-${entry.status}`}>
            <div className="cmd-log-meta">
              <span className="cmd-log-time">{entry.time}</span>
              <span className={`cmd-log-status cmd-log-status-${entry.status}`}>
                {entry.status.toUpperCase()}
              </span>
            </div>
            <div className="cmd-log-command">
              <span className="cmd-log-prompt">&gt;</span> {entry.command}
            </div>
            {entry.response && (
              <div className="cmd-log-response">{entry.response}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

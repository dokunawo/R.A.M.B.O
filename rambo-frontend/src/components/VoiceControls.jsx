import React, { useState, useEffect, useRef, useCallback } from "react";
import { useVoiceReactivity, CONV_STATES, listeningEnabled, voiceTiming } from "./useVoiceReactivity";
import { getVolume, setVolume } from "./audioEngine";
import { frameForGoal, startShare, stopShare, isSharing, armAutoStart } from "./screenVision";
import "./VoiceControls.css";

const API = "http://localhost:8000";

const VOICE_WS_URL = "ws://localhost:8000/ws/activity";

// Phrases that mean "I'm done — stop asking if there's anything else."
const END_PHRASES = [
  "no thank you", "no thanks", "thats it", "that's it", "thats it for now",
  "that's it for now", "thats all", "that's all", "thats all for now",
  "nothing else", "nothing for now", "im good", "i'm good", "im done",
  "i'm done", "im fine", "i'm fine", "all good", "we're good", "were good",
  "that will be all", "that'll be all", "stop", "cancel", "dismiss",
  "no that's all", "no thats all", "nope", "nah", "negative",
];
const SIGN_OFFS = ["Standing by.", "Understood.", "I'm here if you need me.", "Anytime.", "Acknowledged."];

function isEndPhrase(text) {
  const t = (text || "").toLowerCase().trim().replace(/[.,!?]+$/g, "").trim();
  if (!t) return false;
  if (END_PHRASES.includes(t)) return true;
  // bare "no" / "no thanks rambo" style
  if (/^(no|nope|nah)\b/.test(t) && t.length <= 18) return true;
  return false;
}

// Voice command to fully stop listening (mic off, stays off). Distinct from the
// "anything else?" enders above — this kills the mic entirely.
function isStopListening(text) {
  const t = (text || "").toLowerCase().replace(/[.,!?]+$/g, "").trim();
  return /(stop listening|pause listening|stop the mic|mute the mic|mic off|go to sleep|stop the microphone|pause the mic)/.test(t);
}

// Voice command to dismiss all accumulated response cards.
function isClearCommand(text) {
  const t = (text || "").toLowerCase().replace(/[.,!?]+$/g, "").trim();
  return /(clear everything|clear responses|clear all|clear the screen|clear the responses|clear cards|dismiss all)/.test(t);
}

// Voice command to toggle screen share. Returns "on" | "off" | null.
function screenShareIntent(text) {
  const t = (text || "").toLowerCase().replace(/[.,!?]+$/g, "").trim();
  if (!/(screen\s*shar(?:e|ing)|shar(?:e|ing)\s+(?:my|the)\s+screen|screen\s+vision|look\s+at\s+my\s+screen)/.test(t)) return null;
  if (/\b(off|stop|disable|end|kill|close|hide|don'?t)\b/.test(t)) return "off";
  if (/\b(on|start|enable|begin|open|turn\s+on|share)\b/.test(t)) return "on";
  return null;
}

// Voice command to open the Command Center view.
function isCommandCenter(text) {
  const t = (text || "").toLowerCase().replace(/[.,!?]+$/g, "").trim();
  return /(command cent(er|re)|open command cent|go to command cent|main view|home screen|main screen|take me home|go home)/.test(t);
}

export function usePageVoice({ onCommandCenter } = {}) {
  const [voiceText, setVoiceText] = useState("");
  const [commandLog, setCommandLog] = useState([]);
  const [busy, setBusy] = useState(false);
  const voiceSetStateRef = useRef(null);
  const speakRef = useRef(null);
  const segmentHandlerRef = useRef(null);
  const setFollowUpRef = useRef(null);
  const stopListeningRef = useRef(null);
  const onCommandCenterRef = useRef(onCommandCenter);
  onCommandCenterRef.current = onCommandCenter;

  const executeCommand = useCallback(async (text) => {
    if (!text.trim() || busy) return;
    setBusy(true);
    const entry = { id: Date.now(), time: new Date().toLocaleTimeString(), command: text, response: null, status: "processing" };
    setCommandLog(prev => [entry, ...prev].slice(0, 50));

    try {
      const image = frameForGoal(text);  // screen frame when sharing + screen-directed
      voiceTiming.mark("sent");           // request leaving for the backend
      const res = await fetch(`${API}/rambo/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(image ? { goal: text, image } : { goal: text }),
      });
      const data = await res.json().catch(() => ({}));
      const responseText = data.response || "(no response)";
      setCommandLog(prev => prev.map(e =>
        e.id === entry.id ? { ...e, response: responseText, status: "complete" } : e
      ));
    } catch {
      setCommandLog(prev => prev.map(e =>
        e.id === entry.id ? { ...e, response: "Request failed — backend offline", status: "error" } : e
      ));
    } finally {
      setBusy(false);
    }
  }, [busy]);

  const tryVolumeCommand = useCallback((text) => {
    const t = text.toLowerCase().trim();
    // "volume 50", "set volume to 75", "volume at 30"
    let m = t.match(/(?:set\s+)?volume\s+(?:to\s+|at\s+)?(\d{1,3})(?:\s*%)?/);
    if (m) { const v = setVolume(parseInt(m[1], 10)); return `Volume set to ${v}%`; }
    // "mute", "unmute"
    if (/^(?:mute|silence)$/.test(t)) { setVolume(0); return "Muted"; }
    if (/^unmute$/.test(t)) { setVolume(50); return "Volume restored to 50%"; }
    // "lower volume by 20", "reduce volume 10"
    m = t.match(/(?:lower|reduce|decrease|turn\s+down)\s+(?:the\s+)?volume\s+(?:by\s+)?(\d{1,3})(?:\s*%)?/);
    if (m) { const v = setVolume(getVolume() - parseInt(m[1], 10)); return `Volume lowered to ${v}%`; }
    // "raise volume by 20", "increase volume 10"
    m = t.match(/(?:raise|increase|turn\s+up)\s+(?:the\s+)?volume\s+(?:by\s+)?(\d{1,3})(?:\s*%)?/);
    if (m) { const v = setVolume(getVolume() + parseInt(m[1], 10)); return `Volume raised to ${v}%`; }
    // bare number while talking about volume context — "50", "75"
    if (/^\d{1,3}$/.test(t)) {
      const n = parseInt(t, 10);
      if (n >= 0 && n <= 100) { const v = setVolume(n); return `Volume set to ${v}%`; }
    }
    return null;
  }, []);

  const handleFinalTranscript = useCallback((text) => {
    setVoiceText(text);

    // Soft pause: drop to wake-gated idle and ignore ambient audio until the
    // operator says the wake word again. Mic stays on so it can hear it.
    if (isStopListening(text)) {
      const entry = { id: Date.now(), time: new Date().toLocaleTimeString(), command: text, response: 'Listening paused. Say "Operator" to resume.', status: "complete" };
      setCommandLog(prev => [entry, ...prev].slice(0, 50));
      if (stopListeningRef.current) stopListeningRef.current();
      return;
    }

    // Clear all accumulated response cards on this page.
    if (isClearCommand(text)) {
      setCommandLog([]);
      if (voiceSetStateRef.current) voiceSetStateRef.current(CONV_STATES.IDLE);
      return;
    }

    // Toggle screen share hands-free. "off" always works; "on" needs a user
    // gesture (Chrome rule for getDisplayMedia) — if blocked, we arm auto-start
    // so the operator's next tap/keypress enables it, and say so.
    const ssIntent = screenShareIntent(text);
    if (ssIntent) {
      (async () => {
        let resp;
        if (ssIntent === "off") {
          stopShare();
          resp = isSharing() ? "Couldn't stop screen share." : "Screen share off.";
        } else if (isSharing()) {
          resp = "Screen share is already on.";
        } else {
          try { await startShare(); resp = "Screen share on."; }
          catch { armAutoStart(); resp = "I can't start screen share on my own — tap anywhere and I'll turn it on."; }
        }
        const entry = { id: Date.now(), time: new Date().toLocaleTimeString(), command: text, response: resp, status: "complete" };
        setCommandLog(prev => [entry, ...prev].slice(0, 50));
        if (speakRef.current) speakRef.current(resp, true);
      })();
      if (voiceSetStateRef.current) voiceSetStateRef.current(CONV_STATES.IDLE);
      return;
    }

    // Open the Command Center hands-free.
    if (isCommandCenter(text)) {
      if (voiceSetStateRef.current) voiceSetStateRef.current(CONV_STATES.IDLE);
      if (onCommandCenterRef.current) onCommandCenterRef.current();
      return;
    }

    // Conversation-ender: if the user declines the "anything else?" follow-up,
    // stop the loop and sign off instead of treating it as a new request.
    if (isEndPhrase(text)) {
      if (setFollowUpRef.current) setFollowUpRef.current(false);
      const signoff = SIGN_OFFS[Math.floor(Math.random() * SIGN_OFFS.length)];
      const entry = { id: Date.now(), time: new Date().toLocaleTimeString(), command: text, response: signoff, status: "complete" };
      setCommandLog(prev => [entry, ...prev].slice(0, 50));
      if (speakRef.current) speakRef.current(signoff, false);   // false = no follow-up, go idle
      return;
    }

    const volResponse = tryVolumeCommand(text);
    if (volResponse) {
      const entry = { id: Date.now(), time: new Date().toLocaleTimeString(), command: text, response: volResponse, status: "complete" };
      setCommandLog(prev => [entry, ...prev].slice(0, 50));
      if (speakRef.current) speakRef.current(volResponse, true);
      return;
    }
    if (setFollowUpRef.current) setFollowUpRef.current(true);
    executeCommand(text);
    if (voiceSetStateRef.current) voiceSetStateRef.current(CONV_STATES.PROCESSING);
  }, [executeCommand, tryVolumeCommand]);

  const voice = useVoiceReactivity({
    onTranscript: setVoiceText,
    onFinalTranscript: handleFinalTranscript,
  });

  voiceSetStateRef.current = voice.setState;
  speakRef.current = voice.speakResponse;
  segmentHandlerRef.current = voice.handleSpeakSegment;
  setFollowUpRef.current = voice.setFollowUp;
  stopListeningRef.current = voice.pauseListening;

  useEffect(() => {
    let ws;
    let closed = false;
    let retry;
    const connect = () => {
      try { ws = new WebSocket(VOICE_WS_URL); } catch { return; }
      ws.onclose = () => { if (!closed) retry = setTimeout(connect, 2500); };
      ws.onerror = () => { try { ws.close(); } catch {} };
      ws.onmessage = (e) => {
        const msg = String(e.data);
        if (msg.charAt(0) !== "{") return;
        try {
          const j = JSON.parse(msg);
          if (j.t === "speak_segment" && segmentHandlerRef.current) {
            segmentHandlerRef.current(j);
          }
        } catch { /* ignore */ }
      };
    };
    connect();
    return () => { closed = true; clearTimeout(retry); try { ws?.close(); } catch {} };
  }, []);

  const started = useRef(false);
  useEffect(() => {
    if (!started.current) {
      started.current = true;
      // Respect a persisted "stop listening" — don't auto-start the mic if the
      // operator turned it off.
      if (listeningEnabled()) setTimeout(() => voice.startMic(), 1200);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const clearCommandLog = useCallback(() => setCommandLog([]), []);

  return { ...voice, voiceText, setVoiceText, speakRef, commandLog, clearCommandLog, executeCommand, busy };
}

export function VoiceControls({ micActive, toggleMic, convState, onPower }) {
  // Volume now lives in the top-right Settings panel (gear icon). Voice commands
  // ("volume 50", "mute", …) still adjust it via setVolume in tryVolumeCommand.
  const isListening = convState === CONV_STATES.LISTENING;
  const isProcessing = convState === CONV_STATES.PROCESSING;
  const isError = convState === CONV_STATES.ERROR;
  const isActive = micActive && (isListening || isProcessing);

  const micClass = [
    "vc-mic-primary",
    isActive ? "vc-mic-active" : "",
    isProcessing ? "vc-mic-processing" : "",
    isError ? "vc-mic-blocked" : "",
  ].filter(Boolean).join(" ");

  return (
    <div className="vc-bar">
      <div className="vc-bar-center">
        <button
          className={micClass}
          type="button"
          onClick={toggleMic}
          title={
            isError ? "Microphone blocked — allow mic access in your browser, then reload"
            : micActive ? 'Mic active — say "Operator" to command'
            : "Enable mic"
          }
        >
          {isError ? (
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="9" y="2" width="6" height="11" rx="3"/>
              <path d="M5 10a7 7 0 0 0 14 0"/>
              <line x1="12" y1="19" x2="12" y2="22"/>
              <line x1="3" y1="3" x2="21" y2="21" stroke="#ff5b5b"/>
            </svg>
          ) : isActive ? (
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <rect x="3" y="3" width="10" height="10" rx="1.5" fill="currentColor"/>
            </svg>
          ) : (
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="9" y="2" width="6" height="11" rx="3"/>
              <path d="M5 10a7 7 0 0 0 14 0"/>
              <line x1="12" y1="19" x2="12" y2="22"/>
            </svg>
          )}
        </button>
      </div>
      {isError ? (
        <span className="vc-hint vc-hint-error">MIC BLOCKED — ALLOW ACCESS &amp; RELOAD</span>
      ) : !isActive ? (
        <span className="vc-hint">TAP OR SAY 'OPERATOR'</span>
      ) : null}
      {onPower && (
        <button className="vc-power-btn" onClick={onPower}
          title='Shut down to standby (or say "shut down")'>⏻</button>
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

import { useRef, useEffect, useCallback, useState } from "react";
import { setVoiceDuck } from "./spotifyEngine";

const SMOOTH_UP   = 0.35;
const SMOOTH_DOWN = 0.08;
const WAKE_WORD   = "operator";
// Wake word: "operator" — recognized far more reliably than "Rambo". Accept a
// couple of close variants just in case.
const WAKE_VARIANTS = ["operator", "operador", "opperator", "operater"];
function matchesWake(text) {
  return WAKE_VARIANTS.some(w => text.includes(w));
}

// Cross-instance guard: if the page remounts and spins up multiple voice
// listeners, only ONE should speak a given reply. Tracks base_turn_ids that are
// already being voiced anywhere so duplicates are dropped (prevents the
// ElevenLabs + browser double-voice).
const globalSpokenTurns = new Set();

// Persisted listening on/off so an explicit stop STICKS across refreshes and
// page navigations (otherwise the mic auto-starts again and keeps picking up
// audio — e.g. while watching a video). Default ON.
export function listeningEnabled() {
  try { return localStorage.getItem("rambo-listening") !== "off"; } catch { return true; }
}
function setListeningPref(on) {
  try { localStorage.setItem("rambo-listening", on ? "on" : "off"); } catch { /* ignore */ }
}

export const CONV_STATES = {
  IDLE:       "idle",
  LISTENING:  "listening",
  PROCESSING: "processing",
  SPEAKING:   "speaking",
  ERROR:      "error",
};

// Global singleton — only one SpeechRecognition instance per tab
let globalRecognition = null;
let globalRecognitionOwner = null;

function stopGlobalRecognition() {
  if (globalRecognition) {
    try { globalRecognition.onend = null; globalRecognition.stop(); } catch {}
    globalRecognition = null;
    globalRecognitionOwner = null;
  }
}

function getPreferredVoice() {
  const voices = window.speechSynthesis?.getVoices() || [];
  return voices.find(v =>
    /google uk english female|microsoft zira|samantha|karen|victoria|fiona/i.test(v.name)
  ) || voices.find(v =>
    /google us english/i.test(v.name)
  ) || voices.find(v => v.lang.startsWith("en") && /female|natural|premium/i.test(v.name)
  ) || voices.find(v => v.lang.startsWith("en")) || voices[0];
}

function speak(text, onStart, onEnd) {
  const synth = window.speechSynthesis;
  if (!synth) { onEnd?.(); return; }
  synth.cancel();
  const utter = new SpeechSynthesisUtterance(text);
  const preferred = getPreferredVoice();
  if (preferred) utter.voice = preferred;
  utter.rate  = 1.0;
  utter.pitch = 1.05;
  utter.volume = 1.0;
  utter.onstart = () => onStart?.();
  utter.onend   = () => onEnd?.();
  utter.onerror = () => onEnd?.();
  synth.speak(utter);
}

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

function speakViaSynth(text) {
  return new Promise((resolve) => {
    const synth = window.speechSynthesis;
    if (!synth) { resolve(); return; }
    const utter = new SpeechSynthesisUtterance(text);
    const preferred = getPreferredVoice();
    if (preferred) utter.voice = preferred;
    utter.rate = 1.0;
    utter.pitch = 1.05;
    utter.volume = 1.0;
    utter.onend = resolve;
    utter.onerror = resolve;
    synth.speak(utter);
  });
}

function speakSegment(seg) {
  const text = typeof seg === "string" ? seg : seg.text;
  const audio = typeof seg === "string" ? null : seg.audio;
  if (audio) {
    return playAudioSegment(audio).then((ok) => {
      if (ok) return;
      return speakViaSynth(text); // fallback if decode/playback failed
    });
  }
  return speakViaSynth(text);
}

if (typeof window !== "undefined" && window.speechSynthesis) {
  window.speechSynthesis.getVoices();
  window.speechSynthesis.onvoiceschanged = () => window.speechSynthesis.getVoices();
}

export function useVoiceReactivity({ onTranscript, onFinalTranscript, onSpeakStart, onSpeakEnd } = {}) {
  const levelRef    = useRef(0);
  const activeRef   = useRef(false);
  const streamRef   = useRef(null);
  const ctxRef      = useRef(null);
  const analyserRef = useRef(null);
  const rafRef      = useRef(null);
  const ownerIdRef  = useRef(Math.random().toString(36));
  const wakeDetectedRef = useRef(false);
  const commandBufferRef = useRef("");
  const silenceTimerRef = useRef(null);
  const recogWatchdogRef = useRef(null);
  // Half-duplex echo suppression: stateRef mirrors `state` for the recognition
  // closure; suppressUntilRef is a timestamp the mic stays muted until (covers
  // the speaker echo tail right after TTS ends).
  const stateRef = useRef(CONV_STATES.IDLE);
  const suppressUntilRef = useRef(0);
  const ECHO_COOLDOWN_MS = 1200;
  const [state, setState]         = useState(CONV_STATES.IDLE);
  const [micActive, setMicActive] = useState(false);
  const [transcript, setTranscript] = useState("");

  // Duck Spotify while R.A.M.B.O is engaged (listening/processing/speaking) so the
  // mic doesn't pick up the music and you can hear R.A.M.B.O over it.
  useEffect(() => {
    setVoiceDuck(state === CONV_STATES.LISTENING
      || state === CONV_STATES.PROCESSING
      || state === CONV_STATES.SPEAKING);
  }, [state]);

  const onTranscriptRef      = useRef(onTranscript);
  const onFinalTranscriptRef = useRef(onFinalTranscript);
  const onSpeakStartRef      = useRef(onSpeakStart);
  const onSpeakEndRef        = useRef(onSpeakEnd);
  useEffect(() => { stateRef.current = state; }, [state]);
  useEffect(() => { onTranscriptRef.current = onTranscript; }, [onTranscript]);
  useEffect(() => { onFinalTranscriptRef.current = onFinalTranscript; }, [onFinalTranscript]);
  useEffect(() => { onSpeakStartRef.current = onSpeakStart; }, [onSpeakStart]);
  useEffect(() => { onSpeakEndRef.current = onSpeakEnd; }, [onSpeakEnd]);

  const tick = useCallback(() => {
    if (!analyserRef.current || !activeRef.current) return;
    const analyser = analyserRef.current;
    const data = new Uint8Array(analyser.frequencyBinCount);
    analyser.getByteFrequencyData(data);
    let sum = 0;
    for (let i = 0; i < data.length; i++) sum += data[i] * data[i];
    const rms = Math.sqrt(sum / data.length) / 255;
    const prev = levelRef.current;
    // While RAMBO is speaking, drive the orb from its own voice instead of mic.
    if (ttsLevel.value > 0) {
      levelRef.current = levelRef.current + 0.3 * (ttsLevel.value - levelRef.current);
    } else {
      const alpha = rms > prev ? SMOOTH_UP : SMOOTH_DOWN;
      levelRef.current = prev + alpha * (rms - prev);
    }
    rafRef.current = requestAnimationFrame(tick);
  }, []);

  const segmentQueueRef = useRef([]);
  const playingSegmentRef = useRef(false);
  const activeBaseTurnRef = useRef(null);
  const followUpRef = useRef(false);

  const finishTurn = useCallback(() => {
    onSpeakEndRef.current?.();
    // Keep ignoring the mic for a moment so the speaker echo tail of the last
    // segment doesn't get picked up as a command.
    suppressUntilRef.current = Date.now() + ECHO_COOLDOWN_MS;
    commandBufferRef.current = "";
    setTranscript("");
    activeBaseTurnRef.current = null;
    if (followUpRef.current) {
      wakeDetectedRef.current = true;
      setState(CONV_STATES.LISTENING);
    } else {
      wakeDetectedRef.current = false;
      setState(CONV_STATES.IDLE);
    }
  }, []);

  const pumpQueue = useCallback(async () => {
    if (playingSegmentRef.current || segmentQueueRef.current.length === 0) return;
    const seg = segmentQueueRef.current.shift();
    playingSegmentRef.current = true;
    await speakSegment(seg);
    playingSegmentRef.current = false;
    if (segmentQueueRef.current.length > 0) {
      pumpQueue();
    } else if (seg.is_final) {
      finishTurn();
    }
  }, [finishTurn]);

  const handleSpeakSegment = useCallback((msg) => {
    if (activeBaseTurnRef.current === null && segmentQueueRef.current.length === 0 && !playingSegmentRef.current) {
      // Another voice listener (from a remount) already claimed this reply — skip
      // so it isn't spoken twice.
      if (globalSpokenTurns.has(msg.base_turn_id)) return;
      globalSpokenTurns.add(msg.base_turn_id);
      if (globalSpokenTurns.size > 50) {
        globalSpokenTurns.delete(globalSpokenTurns.values().next().value);
      }
      activeBaseTurnRef.current = msg.base_turn_id;
      setState(CONV_STATES.SPEAKING);
      onSpeakStartRef.current?.();
    } else if (msg.base_turn_id !== activeBaseTurnRef.current) {
      return;
    }
    segmentQueueRef.current.push(msg);
    pumpQueue();
  }, [pumpQueue]);

  const speakResponse = useCallback((text, followUp = false) => {
    followUpRef.current = followUp;
    if (activeBaseTurnRef.current) return;
    setState(CONV_STATES.SPEAKING);
    onSpeakStartRef.current?.();
    const fullText = followUp ? text + " ... Is there anything else?" : text;
    speak(fullText, null, () => {
      onSpeakEndRef.current?.();
      suppressUntilRef.current = Date.now() + ECHO_COOLDOWN_MS;
      commandBufferRef.current = "";
      setTranscript("");
      if (followUp) {
        wakeDetectedRef.current = true;
        setState(CONV_STATES.LISTENING);
      } else {
        wakeDetectedRef.current = false;
        setState(CONV_STATES.IDLE);
      }
    });
  }, []);

  const setupRecognition = useCallback(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) return;

    // Kill any existing instance from any hook
    stopGlobalRecognition();

    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-US";
    recognition.maxAlternatives = 3;

    recognition.onresult = (event) => {
      if (globalRecognitionOwner !== ownerIdRef.current) return;

      // Half-duplex: while R.A.M.B.O is speaking (and for a brief cooldown
      // after), discard everything the mic hears — otherwise its own TTS
      // coming out of the speakers gets transcribed as a new command.
      if (stateRef.current === CONV_STATES.SPEAKING || Date.now() < suppressUntilRef.current) {
        return;
      }

      let interim = "";
      let finalText = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const t = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalText += t;
        } else {
          interim += t;
        }
      }

      const combined = (finalText || interim).toLowerCase().trim();

      if (!wakeDetectedRef.current) {
        if (matchesWake(combined)) {
          wakeDetectedRef.current = true;
          setState(CONV_STATES.LISTENING);
          const idx = combined.indexOf(WAKE_WORD);
          const after = combined.slice(idx + WAKE_WORD.length).trim();
          if (after) {
            commandBufferRef.current = after;
            setTranscript(after);
            onTranscriptRef.current?.(after);
          }
          return;
        }
      } else {
        if (finalText) {
          let cmd = finalText.trim();
          const lower = cmd.toLowerCase();
          if (lower.startsWith(WAKE_WORD)) cmd = cmd.slice(WAKE_WORD.length).trim();
          cmd = cmd.replace(/^[,.\s]+/, "");
          if (cmd) {
            commandBufferRef.current = cmd;
            setTranscript(cmd);
            onTranscriptRef.current?.(cmd);
            if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
            silenceTimerRef.current = setTimeout(() => {
              const finalCmd = commandBufferRef.current.trim();
              if (finalCmd) onFinalTranscriptRef.current?.(finalCmd);
            }, 1000);
          }
        } else if (interim) {
          let cmd = interim.trim();
          const lower = cmd.toLowerCase();
          if (lower.startsWith(WAKE_WORD)) cmd = cmd.slice(WAKE_WORD.length).trim();
          cmd = cmd.replace(/^[,.\s]+/, "");
          if (cmd) {
            commandBufferRef.current = cmd;
            setTranscript(cmd);
            onTranscriptRef.current?.(cmd);
          }
          if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
          silenceTimerRef.current = setTimeout(() => {
            const finalCmd = commandBufferRef.current.trim();
            if (finalCmd) onFinalTranscriptRef.current?.(finalCmd);
          }, 1000);
        }
      }
    };

    recognition.onerror = (event) => {
      if (event.error === "not-allowed") {
        console.error("[Voice] Microphone permission denied");
        setState(CONV_STATES.ERROR);
        return;
      }
      if (event.error !== "no-speech" && event.error !== "aborted") {
        console.warn("[Voice] Recognition error:", event.error);
      }
    };

    recognition.onend = () => {
      if (activeRef.current && globalRecognitionOwner === ownerIdRef.current) {
        setTimeout(() => {
          if (activeRef.current && globalRecognition === recognition) {
            try { recognition.start(); } catch (e) {
              console.warn("[Voice] Restart failed:", e.message);
            }
          }
        }, 100);
      }
    };

    try {
      recognition.start();
      globalRecognition = recognition;
      globalRecognitionOwner = ownerIdRef.current;
    } catch (e) {
      console.error("[Voice] Could not start recognition:", e.message);
    }
  }, []);

  const startMic = useCallback(async () => {
    if (activeRef.current) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.4;
      source.connect(analyser);

      streamRef.current = stream;
      ctxRef.current = ctx;
      analyserRef.current = analyser;
      activeRef.current = true;
      setMicActive(true);
      setState(CONV_STATES.IDLE);
      wakeDetectedRef.current = false;
      rafRef.current = requestAnimationFrame(tick);

      // Unlock the TTS audio context now that we have a user-gesture-backed mic
      // grant, so ElevenLabs playback never silently fails and falls back to the
      // browser voice.
      const tctx = ensureTtsCtx();
      if (tctx && tctx.state === "suspended") tctx.resume().catch(() => {});

      setupRecognition();

      // Watchdog: browser speech recognition degrades over a long continuous
      // session (mishears, or silently stops), forcing a manual mic re-click.
      // Recycle the recognizer periodically — but only while idle, so an active
      // command is never cut off.
      if (recogWatchdogRef.current) clearInterval(recogWatchdogRef.current);
      recogWatchdogRef.current = setInterval(() => {
        if (!activeRef.current) return;
        if (stateRef.current === CONV_STATES.IDLE && !wakeDetectedRef.current) {
          setupRecognition();
        }
      }, 25000);
    } catch (err) {
      console.error("[Voice] Mic error:", err);
      setState(CONV_STATES.ERROR);
      setMicActive(false);
    }
  }, [tick, setupRecognition]);

  const stopMic = useCallback(() => {
    activeRef.current = false;
    setMicActive(false);
    wakeDetectedRef.current = false;
    commandBufferRef.current = "";
    segmentQueueRef.current = [];
    playingSegmentRef.current = false;
    activeBaseTurnRef.current = null;
    if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
    if (recogWatchdogRef.current) { clearInterval(recogWatchdogRef.current); recogWatchdogRef.current = null; }
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    // Force-stop the recognizer unconditionally. After a remount the global
    // owner id can drift, so guarding the stop on ownership could leave the mic
    // running. An explicit stop must always actually stop.
    stopGlobalRecognition();
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
      streamRef.current = null;
    }
    if (ctxRef.current) {
      ctxRef.current.close();
      ctxRef.current = null;
    }
    analyserRef.current = null;
    levelRef.current = 0;
    setTranscript("");
    setState(CONV_STATES.IDLE);
    window.speechSynthesis?.cancel();
  }, []);

  // Explicit, persisted stop/start. stopListening() guarantees the mic is off
  // and STAYS off (survives refresh/navigation) until startListening() is called.
  const stopListening = useCallback(() => {
    setListeningPref(false);
    stopMic();
  }, [stopMic]);

  // Soft pause for the voice command: the recognizer stays running (so the wake
  // word can resume it hands-free), but it drops back to wake-gated idle and
  // ignores everything until it hears "Operator" again. Cancels any follow-up
  // open-listening so ambient audio (e.g. a video) is no longer acted on.
  const pauseListening = useCallback(() => {
    wakeDetectedRef.current = false;
    followUpRef.current = false;
    commandBufferRef.current = "";
    segmentQueueRef.current = [];
    activeBaseTurnRef.current = null;
    if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
    setTranscript("");
    setState(CONV_STATES.IDLE);
    window.speechSynthesis?.cancel();
  }, []);

  const startListening = useCallback(() => {
    setListeningPref(true);
    startMic();
  }, [startMic]);

  const toggleMic = useCallback(() => {
    if (activeRef.current) stopListening();
    else startListening();
  }, [startListening, stopListening]);

  useEffect(() => {
    return () => {
      activeRef.current = false;
      if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
      if (recogWatchdogRef.current) { clearInterval(recogWatchdogRef.current); recogWatchdogRef.current = null; }
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      if (globalRecognitionOwner === ownerIdRef.current) {
        stopGlobalRecognition();
      }
      if (streamRef.current) streamRef.current.getTracks().forEach(t => t.stop());
      if (ctxRef.current) ctxRef.current.close();
      window.speechSynthesis?.cancel();
    };
  }, []);

  return {
    levelRef, state, setState, micActive, transcript,
    startMic, stopMic, toggleMic, startListening, stopListening, pauseListening,
    speakResponse, handleSpeakSegment,
    setFollowUp: (v) => { followUpRef.current = !!v; },
  };
}

// useVoiceReactivity.js — Tier 3: microphone audio reactivity + speech-to-text.
// Returns a smoothed audio level (0..1), speech transcript, and conversational state.
import { useRef, useEffect, useCallback, useState } from "react";

const SMOOTH_UP   = 0.35;
const SMOOTH_DOWN = 0.08;

export const CONV_STATES = {
  IDLE:       "idle",
  LISTENING:  "listening",
  PROCESSING: "processing",
  SPEAKING:   "speaking",
  ERROR:      "error",
};

export function useVoiceReactivity({ onTranscript, onFinalTranscript } = {}) {
  const levelRef    = useRef(0);
  const activeRef   = useRef(false);
  const streamRef   = useRef(null);
  const ctxRef      = useRef(null);
  const analyserRef = useRef(null);
  const rafRef      = useRef(null);
  const recognitionRef = useRef(null);
  const [state, setState]       = useState(CONV_STATES.IDLE);
  const [micActive, setMicActive] = useState(false);
  const [transcript, setTranscript] = useState("");

  // Stable callback refs so we don't re-create recognition on every render
  const onTranscriptRef = useRef(onTranscript);
  const onFinalTranscriptRef = useRef(onFinalTranscript);
  useEffect(() => { onTranscriptRef.current = onTranscript; }, [onTranscript]);
  useEffect(() => { onFinalTranscriptRef.current = onFinalTranscript; }, [onFinalTranscript]);

  const tick = useCallback(() => {
    if (!analyserRef.current || !activeRef.current) return;
    const analyser = analyserRef.current;
    const data = new Uint8Array(analyser.frequencyBinCount);
    analyser.getByteFrequencyData(data);
    let sum = 0;
    for (let i = 0; i < data.length; i++) sum += data[i] * data[i];
    const rms = Math.sqrt(sum / data.length) / 255;
    const prev = levelRef.current;
    const alpha = rms > prev ? SMOOTH_UP : SMOOTH_DOWN;
    levelRef.current = prev + alpha * (rms - prev);
    rafRef.current = requestAnimationFrame(tick);
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
      setState(CONV_STATES.LISTENING);
      rafRef.current = requestAnimationFrame(tick);

      // Speech recognition
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (SpeechRecognition) {
        const recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = "en-US";

        recognition.onresult = (event) => {
          let interim = "";
          let final = "";
          for (let i = event.resultIndex; i < event.results.length; i++) {
            const t = event.results[i][0].transcript;
            if (event.results[i].isFinal) {
              final += t;
            } else {
              interim += t;
            }
          }

          if (final) {
            setTranscript(final.trim());
            if (onTranscriptRef.current) onTranscriptRef.current(final.trim());
            if (onFinalTranscriptRef.current) onFinalTranscriptRef.current(final.trim());
          } else if (interim) {
            setTranscript(interim);
            if (onTranscriptRef.current) onTranscriptRef.current(interim);
          }
        };

        recognition.onerror = (event) => {
          if (event.error !== "no-speech") {
            console.warn("[SpeechRecognition]", event.error);
          }
        };

        recognition.onend = () => {
          // Restart if still active (browser stops after silence)
          if (activeRef.current && recognitionRef.current) {
            try { recognitionRef.current.start(); } catch {}
          }
        };

        recognition.start();
        recognitionRef.current = recognition;
      }
    } catch (err) {
      console.error("[useVoiceReactivity] mic error:", err);
      setState(CONV_STATES.ERROR);
      setMicActive(false);
    }
  }, [tick]);

  const stopMic = useCallback(() => {
    activeRef.current = false;
    setMicActive(false);
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    if (recognitionRef.current) {
      try { recognitionRef.current.stop(); } catch {}
      recognitionRef.current = null;
    }
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
  }, []);

  const toggleMic = useCallback(() => {
    if (activeRef.current) stopMic();
    else startMic();
  }, [startMic, stopMic]);

  useEffect(() => {
    return () => {
      activeRef.current = false;
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      if (recognitionRef.current) { try { recognitionRef.current.stop(); } catch {} }
      if (streamRef.current) streamRef.current.getTracks().forEach(t => t.stop());
      if (ctxRef.current) ctxRef.current.close();
    };
  }, []);

  return {
    levelRef,
    state,
    setState,
    micActive,
    transcript,
    startMic,
    stopMic,
    toggleMic,
  };
}

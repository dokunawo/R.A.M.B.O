// useVoiceReactivity.js — Tier 3: microphone audio reactivity for the cosmic orb.
// Returns a smoothed audio level (0..1) that drives orb displacement and glow.
// Falls back to synthetic breathing when mic is unavailable or denied.
import { useRef, useEffect, useCallback, useState } from "react";

const SMOOTH_UP   = 0.35;  // fast attack
const SMOOTH_DOWN = 0.08;  // slow decay — asymmetric smoothing

export const CONV_STATES = {
  IDLE:       "idle",
  LISTENING:  "listening",
  PROCESSING: "processing",
  SPEAKING:   "speaking",
  ERROR:      "error",
};

export function useVoiceReactivity() {
  const levelRef   = useRef(0);   // smoothed 0..1
  const rawRef     = useRef(0);
  const activeRef  = useRef(false);
  const streamRef  = useRef(null);
  const ctxRef     = useRef(null);
  const analyserRef = useRef(null);
  const rafRef     = useRef(null);
  const [state, setState] = useState(CONV_STATES.IDLE);
  const [micActive, setMicActive] = useState(false);

  const tick = useCallback(() => {
    if (!analyserRef.current || !activeRef.current) return;

    const analyser = analyserRef.current;
    const data = new Uint8Array(analyser.frequencyBinCount);
    analyser.getByteFrequencyData(data);

    // RMS-ish level from frequency bins
    let sum = 0;
    for (let i = 0; i < data.length; i++) sum += data[i] * data[i];
    const rms = Math.sqrt(sum / data.length) / 255;

    rawRef.current = rms;

    // Asymmetric smoothing: fast attack, slow decay
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
    } catch {
      setState(CONV_STATES.ERROR);
      setMicActive(false);
    }
  }, [tick]);

  const stopMic = useCallback(() => {
    activeRef.current = false;
    setMicActive(false);
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
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
    setState(CONV_STATES.IDLE);
  }, []);

  const toggleMic = useCallback(() => {
    if (activeRef.current) stopMic();
    else startMic();
  }, [startMic, stopMic]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      activeRef.current = false;
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      if (streamRef.current) streamRef.current.getTracks().forEach(t => t.stop());
      if (ctxRef.current) ctxRef.current.close();
    };
  }, []);

  return {
    levelRef,       // ref to smoothed 0..1 — read in useFrame
    state,          // conversational state string
    setState,       // set state externally (processing/speaking)
    micActive,      // boolean: is mic streaming
    startMic,
    stopMic,
    toggleMic,
  };
}

// useVoiceReactivity.js — Voice system: wake word "Rambo", speech-to-text,
// TTS response with cosmic AI voice, and audio-level reactivity for the orb.
import { useRef, useEffect, useCallback, useState } from "react";

const SMOOTH_UP   = 0.35;
const SMOOTH_DOWN = 0.08;
const WAKE_WORD   = "rambo";

export const CONV_STATES = {
  IDLE:       "idle",        // passive listening for wake word
  LISTENING:  "listening",   // wake word detected — capturing command
  PROCESSING: "processing",  // command captured — executing
  SPEAKING:   "speaking",    // reading response aloud
  ERROR:      "error",
};

// ---- TTS: cosmic AI voice ----
function speak(text, onStart, onEnd) {
  const synth = window.speechSynthesis;
  if (!synth) { onEnd?.(); return; }

  // Cancel any ongoing speech
  synth.cancel();

  const utter = new SpeechSynthesisUtterance(text);

  // Pick the most robotic/neutral voice available
  const voices = synth.getVoices();
  // Prefer natural/premium voices for human-like speech
  const preferred = voices.find(v =>
    /google uk english female|microsoft zira|samantha|karen|victoria|fiona/i.test(v.name)
  ) || voices.find(v =>
    /google us english/i.test(v.name)
  ) || voices.find(v => v.lang.startsWith("en") && /female|natural|premium/i.test(v.name)
  ) || voices.find(v => v.lang.startsWith("en")) || voices[0];
  if (preferred) utter.voice = preferred;

  utter.rate  = 1.0;    // natural speaking speed
  utter.pitch = 1.05;   // slightly higher for clarity and warmth
  utter.volume = 1.0;

  utter.onstart = () => onStart?.();
  utter.onend   = () => onEnd?.();
  utter.onerror = () => onEnd?.();

  synth.speak(utter);
}

// Preload voices (Chrome loads them async)
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
  const recognitionRef = useRef(null);
  const wakeDetectedRef = useRef(false);
  const commandBufferRef = useRef("");
  const silenceTimerRef = useRef(null);
  const [state, setState]         = useState(CONV_STATES.IDLE);
  const [micActive, setMicActive] = useState(false);
  const [transcript, setTranscript] = useState("");

  const onTranscriptRef      = useRef(onTranscript);
  const onFinalTranscriptRef = useRef(onFinalTranscript);
  const onSpeakStartRef      = useRef(onSpeakStart);
  const onSpeakEndRef        = useRef(onSpeakEnd);
  useEffect(() => { onTranscriptRef.current = onTranscript; }, [onTranscript]);
  useEffect(() => { onFinalTranscriptRef.current = onFinalTranscript; }, [onFinalTranscript]);
  useEffect(() => { onSpeakStartRef.current = onSpeakStart; }, [onSpeakStart]);
  useEffect(() => { onSpeakEndRef.current = onSpeakEnd; }, [onSpeakEnd]);

  // Audio level tick for orb animation
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

  // Speak a response aloud with the cosmic voice
  // If followUp=true, ask "Is there anything else?" and go to LISTENING (no wake word)
  const speakResponse = useCallback((text, followUp = false) => {
    setState(CONV_STATES.SPEAKING);
    onSpeakStartRef.current?.();

    const fullText = followUp ? text + " ... Is there anything else?" : text;

    speak(fullText, null, () => {
      onSpeakEndRef.current?.();
      commandBufferRef.current = "";
      setTranscript("");

      if (followUp) {
        // Go straight to listening — no wake word needed for follow-up
        wakeDetectedRef.current = true;
        setState(CONV_STATES.LISTENING);
      } else {
        wakeDetectedRef.current = false;
        setState(CONV_STATES.IDLE);
      }
    });
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

      // Speech recognition — always on, listening for wake word then command
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (SpeechRecognition) {
        const recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = "en-US";

        recognition.onresult = (event) => {
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
            // Passive mode: scan for wake word
            if (combined.includes(WAKE_WORD)) {
              wakeDetectedRef.current = true;
              setState(CONV_STATES.LISTENING);

              // Extract everything after "rambo" as the start of the command
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
            // Active mode: capturing command after wake word
            if (finalText) {
              // Strip wake word if it appears at the start of the final text
              let cmd = finalText.trim();
              const lower = cmd.toLowerCase();
              if (lower.startsWith(WAKE_WORD)) {
                cmd = cmd.slice(WAKE_WORD.length).trim();
              }
              // Remove leading punctuation/filler
              cmd = cmd.replace(/^[,.\s]+/, "");

              if (cmd) {
                commandBufferRef.current = cmd;
                setTranscript(cmd);
                onTranscriptRef.current?.(cmd);

                // Wait for a silence gap — if no new speech in 1.5s, finalize
                if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
                silenceTimerRef.current = setTimeout(() => {
                  const finalCmd = commandBufferRef.current.trim();
                  if (finalCmd) {
                    onFinalTranscriptRef.current?.(finalCmd);
                  }
                }, 1500);
              }
            } else if (interim) {
              let cmd = interim.trim();
              const lower = cmd.toLowerCase();
              if (lower.startsWith(WAKE_WORD)) {
                cmd = cmd.slice(WAKE_WORD.length).trim();
              }
              cmd = cmd.replace(/^[,.\s]+/, "");

              if (cmd) {
                commandBufferRef.current = cmd;
                setTranscript(cmd);
                onTranscriptRef.current?.(cmd);
              }

              // Reset silence timer on interim results
              if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
              silenceTimerRef.current = setTimeout(() => {
                const finalCmd = commandBufferRef.current.trim();
                if (finalCmd) {
                  onFinalTranscriptRef.current?.(finalCmd);
                }
              }, 1500);
            }
          }
        };

        recognition.onerror = (event) => {
          if (event.error !== "no-speech" && event.error !== "aborted") {
            console.warn("[SpeechRecognition]", event.error);
          }
        };

        recognition.onend = () => {
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
    wakeDetectedRef.current = false;
    commandBufferRef.current = "";
    if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
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
    window.speechSynthesis?.cancel();
  }, []);

  const toggleMic = useCallback(() => {
    if (activeRef.current) stopMic();
    else startMic();
  }, [startMic, stopMic]);

  useEffect(() => {
    return () => {
      activeRef.current = false;
      if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      if (recognitionRef.current) { try { recognitionRef.current.stop(); } catch {} }
      if (streamRef.current) streamRef.current.getTracks().forEach(t => t.stop());
      if (ctxRef.current) ctxRef.current.close();
      window.speechSynthesis?.cancel();
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
    speakResponse,
  };
}

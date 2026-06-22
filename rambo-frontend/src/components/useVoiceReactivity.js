import { useRef, useEffect, useCallback, useState } from "react";

const SMOOTH_UP   = 0.35;
const SMOOTH_DOWN = 0.08;
const WAKE_WORD   = "rambo";

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

function speak(text, onStart, onEnd) {
  const synth = window.speechSynthesis;
  if (!synth) { onEnd?.(); return; }
  synth.cancel();
  const utter = new SpeechSynthesisUtterance(text);
  const voices = synth.getVoices();
  const preferred = voices.find(v =>
    /google uk english female|microsoft zira|samantha|karen|victoria|fiona/i.test(v.name)
  ) || voices.find(v =>
    /google us english/i.test(v.name)
  ) || voices.find(v => v.lang.startsWith("en") && /female|natural|premium/i.test(v.name)
  ) || voices.find(v => v.lang.startsWith("en")) || voices[0];
  if (preferred) utter.voice = preferred;
  utter.rate  = 1.0;
  utter.pitch = 1.05;
  utter.volume = 1.0;
  utter.onstart = () => onStart?.();
  utter.onend   = () => onEnd?.();
  utter.onerror = () => onEnd?.();
  synth.speak(utter);
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

  const speakResponse = useCallback((text, followUp = false) => {
    setState(CONV_STATES.SPEAKING);
    onSpeakStartRef.current?.();
    const fullText = followUp ? text + " ... Is there anything else?" : text;
    speak(fullText, null, () => {
      onSpeakEndRef.current?.();
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
        if (combined.includes(WAKE_WORD)) {
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
            }, 1500);
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
          }, 1500);
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

      setupRecognition();
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
    if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    if (globalRecognitionOwner === ownerIdRef.current) {
      stopGlobalRecognition();
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
    startMic, stopMic, toggleMic, speakResponse,
  };
}

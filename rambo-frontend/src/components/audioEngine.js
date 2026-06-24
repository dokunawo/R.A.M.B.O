// audioEngine.js — Web Audio for the synthesized ambient hum + per-keystroke
// click, plus HTMLAudio for the real sound files (void-portal intro,
// access-approved voice). A single `muted` flag (persisted) gates everything;
// browsers still require a user gesture before any of it can actually play.

const INTRO  = "/sounds/intro.mp3";
const ACCESS = "/sounds/access-approved.mp3";

let ctx = null;
let master = null;
let hum = null;
let lastKey = 0; // throttle for the synthesized keystroke click
const files = {}; // url -> HTMLAudioElement

let muted = false;
let volume = 50; // 0-100 percentage
try { muted = localStorage.getItem("rambo-muted") === "1"; } catch { /* ignore */ }
try { const v = parseInt(localStorage.getItem("rambo-volume"), 10); if (v >= 0 && v <= 100) volume = v; } catch { /* ignore */ }

// Fresh machine boot: the startup script opens the app with ?boot=1 so an
// accidentally-persisted mute (or low volume) never carries across a restart —
// it always boots unmuted at max. A normal manual refresh has no ?boot flag, so
// your in-session volume/mute choices are preserved. The flag is then stripped
// from the URL so a refresh of the boot tab doesn't keep resetting.
try {
  if (typeof window !== "undefined") {
    const params = new URLSearchParams(window.location.search);
    if (params.get("boot") === "1") {
      muted = false;
      volume = 100;
      localStorage.setItem("rambo-muted", "0");
      localStorage.setItem("rambo-volume", "100");
      params.delete("boot");
      const qs = params.toString();
      const clean = window.location.pathname + (qs ? "?" + qs : "") + window.location.hash;
      window.history.replaceState({}, "", clean);
    }
  }
} catch { /* ignore */ }

function ensureCtx() {
  if (typeof window === "undefined") return null;
  const AC = window.AudioContext || window.webkitAudioContext;
  if (!AC) return null;
  if (!ctx) {
    try { ctx = new AC(); } catch { return null; }
    master = ctx.createGain();
    master.gain.value = muted ? 0 : volume / 100;
    master.connect(ctx.destination);
  }
  return ctx;
}

function getFile(url, { loop = false, volume = 1 } = {}) {
  let a = files[url];
  if (!a) {
    a = new Audio(url);
    a.preload = "auto";
    files[url] = a;
  }
  a.loop = loop;
  a.volume = volume;
  a.muted = muted;
  return a;
}

export function resumeAudio() {
  const c = ensureCtx();
  if (c && c.state === "suspended") c.resume().catch(() => {});
  return !!c && c.state === "running";
}

export function audioRunning() {
  return !!ctx && ctx.state === "running";
}

// Sound on by default: auto-enable audio on the EARLIEST user interaction
// anywhere in the app (browsers require one gesture before audio can start, so
// this grabs the first one — a click, tap, or keypress you'd make anyway). The
// kiosk launcher unlocks autoplay so this isn't even needed there; in a normal
// tab it means the "ENABLE SOUND" gate self-dismisses on first interaction
// instead of needing a deliberate click.
if (typeof window !== "undefined") {
  const _armEvents = ["pointerdown", "keydown", "touchstart", "click"];
  const _armOnce = () => {
    if (muted) return;            // respect an explicit disable
    resumeAudio();
    if (audioRunning()) {
      _armEvents.forEach(ev => window.removeEventListener(ev, _armOnce));
    }
  };
  _armEvents.forEach(ev => window.addEventListener(ev, _armOnce, { passive: true }));
}

export function isMuted() { return muted; }

export function setMuted(v) {
  muted = !!v;
  try { localStorage.setItem("rambo-muted", muted ? "1" : "0"); } catch { /* ignore */ }
  if (master) master.gain.value = muted ? 0 : volume / 100;
  Object.values(files).forEach(a => { a.muted = muted; });
  return muted;
}

export function getVolume() { return volume; }

export function setVolume(pct) {
  volume = Math.max(0, Math.min(100, Math.round(pct)));
  try { localStorage.setItem("rambo-volume", String(volume)); } catch { /* ignore */ }
  if (volume === 0) {
    muted = true;
    try { localStorage.setItem("rambo-muted", "1"); } catch { /* ignore */ }
  } else if (muted) {
    muted = false;
    try { localStorage.setItem("rambo-muted", "0"); } catch { /* ignore */ }
  }
  if (master) master.gain.value = muted ? 0 : volume / 100;
  Object.values(files).forEach(a => {
    a.muted = muted;
    a.volume = volume / 100;
  });
  return volume;
}

/* ---------------- real sound files ---------------- */

// Intro HUD sound — preload so the vortex can read the duration early.
export function loadIntro() {
  return getFile(INTRO, { loop: false, volume: 0.6 });
}

export function playIntro() {
  const a = getFile(INTRO, { loop: false, volume: 0.6 });
  try { a.currentTime = 0; a.play().catch(() => {}); } catch { /* ignore */ }
  return a;
}

// "Access approved" robot voice — preload to read its length, then play.
export function loadAccessApproved() {
  return getFile(ACCESS, { loop: false, volume: 0.85 });
}

export function playAccessApproved() {
  const a = getFile(ACCESS, { loop: false, volume: 0.85 });
  try { a.currentTime = 0; a.play().catch(() => {}); } catch { /* ignore */ }
  return a;
}

// Synthesized typewriter keystroke — a short percussive noise click. Called
// once per character as text types, lightly throttled so it stays crisp.
export function playKeyClick() {
  const c = ensureCtx();
  if (!c || c.state !== "running" || !master || muted) return;
  const now = c.currentTime;
  if (now - lastKey < 0.02) return; // throttle
  lastKey = now;

  const dur = 0.028;
  const buf = c.createBuffer(1, Math.ceil(c.sampleRate * dur), c.sampleRate);
  const data = buf.getChannelData(0);
  for (let i = 0; i < data.length; i++) {
    data[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / data.length, 3); // sharp decay
  }
  const src = c.createBufferSource();
  src.buffer = buf;
  const bp = c.createBiquadFilter();
  bp.type = "bandpass";
  bp.frequency.value = 1900;
  bp.Q.value = 0.9;
  const g = c.createGain();
  g.gain.value = 0.28;
  src.connect(bp);
  bp.connect(g);
  g.connect(master);
  src.start(now);
  src.stop(now + dur);
}

/* ---------------- synthesized ambient hum (console) ---------------- */

export function startHum() {
  const c = ensureCtx();
  if (!c || c.state !== "running" || !master || hum) return;

  const gain = c.createGain();
  gain.gain.value = 0.0001;

  const lp = c.createBiquadFilter();
  lp.type = "lowpass";
  lp.frequency.value = 380;
  lp.Q.value = 0.2;

  const oscs = [
    { f: 110, d: -3 },  // A2
    { f: 165, d: 4 },   // E3
  ].map(({ f, d }) => {
    const o = c.createOscillator();
    o.type = "sine";
    o.frequency.value = f;
    o.detune.value = d;
    o.connect(lp);
    o.start();
    return o;
  });

  lp.connect(gain);
  gain.connect(master);

  const lfo = c.createOscillator();
  const lfoGain = c.createGain();
  lfo.type = "sine";
  lfo.frequency.value = 0.08;
  lfoGain.gain.value = 0.001;
  lfo.connect(lfoGain);
  lfoGain.connect(gain.gain);
  lfo.start();

  gain.gain.linearRampToValueAtTime(0.006, c.currentTime + 3.0);

  hum = { oscs, lfo, gain };
}

export function stopHum() {
  const c = ensureCtx();
  if (!c || !hum) return;
  const { oscs, lfo, gain } = hum;
  hum = null;
  try {
    gain.gain.cancelScheduledValues(c.currentTime);
    gain.gain.setValueAtTime(gain.gain.value, c.currentTime);
    gain.gain.linearRampToValueAtTime(0.0001, c.currentTime + 0.8);
    oscs.forEach(o => o.stop(c.currentTime + 0.9));
    lfo.stop(c.currentTime + 0.9);
  } catch {
    /* ignore */
  }
}

// audioEngine.js — tiny Web Audio helper. No asset files: a boot chime and a
// low ambient hum are synthesized. Browsers block audio until a user gesture,
// so call resumeAudio() from a gesture handler once.

let ctx = null;
let humNodes = null;

function ensureCtx() {
  if (typeof window === "undefined") return null;
  const AC = window.AudioContext || window.webkitAudioContext;
  if (!AC) return null;
  if (!ctx) {
    try { ctx = new AC(); } catch { return null; }
  }
  return ctx;
}

export function resumeAudio() {
  const c = ensureCtx();
  if (c && c.state === "suspended") c.resume().catch(() => {});
}

// Two ascending sine blips — a short "system online" chime.
export function playChime() {
  const c = ensureCtx();
  if (!c) return;
  if (c.state === "suspended") c.resume().catch(() => {});
  const now = c.currentTime;
  [[523.25, 0.0], [783.99, 0.13]].forEach(([freq, t]) => {
    const o = c.createOscillator();
    const g = c.createGain();
    o.type = "sine";
    o.frequency.value = freq;
    g.gain.setValueAtTime(0.0001, now + t);
    g.gain.linearRampToValueAtTime(0.16, now + t + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, now + t + 0.5);
    o.connect(g);
    g.connect(c.destination);
    o.start(now + t);
    o.stop(now + t + 0.55);
  });
}

// Low ambient hum (a root + fifth through a lowpass) that fades in.
export function startHum() {
  const c = ensureCtx();
  if (!c || humNodes) return;
  if (c.state === "suspended") c.resume().catch(() => {});

  const gain = c.createGain();
  gain.gain.value = 0.0001;

  const filter = c.createBiquadFilter();
  filter.type = "lowpass";
  filter.frequency.value = 220;

  const oscs = [72, 108].map((f, i) => {
    const o = c.createOscillator();
    o.type = "sine";
    o.frequency.value = f;
    o.detune.value = i === 0 ? -4 : 5;
    o.connect(filter);
    o.start();
    return o;
  });

  filter.connect(gain);
  gain.connect(c.destination);
  gain.gain.linearRampToValueAtTime(0.045, c.currentTime + 1.4);

  humNodes = { oscs, gain };
}

export function stopHum() {
  const c = ensureCtx();
  if (!c || !humNodes) return;
  const { oscs, gain } = humNodes;
  humNodes = null;
  try {
    gain.gain.linearRampToValueAtTime(0.0001, c.currentTime + 0.5);
    oscs.forEach(o => o.stop(c.currentTime + 0.6));
  } catch {
    /* ignore */
  }
}

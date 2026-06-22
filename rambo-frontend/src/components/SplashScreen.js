// SplashScreen.js
import React, { useState, useEffect, useRef, useCallback } from "react";
import { Canvas } from "@react-three/fiber";
import { EffectComposer, Bloom, ChromaticAberration } from "@react-three/postprocessing";
import { Vector2 } from "three";
import RamboOrb3D from "./RamboOrb3D";
import {
  resumeAudio, audioRunning, startHum, stopHum,
  loadIntro, playIntro, playKeyClick,
  isMuted, setMuted,
} from "./audioEngine";
import "./SplashScreen.css";

/* ------------------------------------------------------------------ */
/*  CONSTANTS                                                           */
/* ------------------------------------------------------------------ */

const AGENT_ROSTER = [
  { key: "architect", name: "Architect", role: "Strategic Planning",  desc: "Decomposes goals into executable task hierarchies" },
  { key: "engineer",  name: "Engineer",  role: "Code Execution",      desc: "Generates and executes technical implementations" },
  { key: "seeker",    name: "Seeker",    role: "Intelligence",         desc: "Researches and retrieves critical information" },
  { key: "analyst",   name: "Analyst",   role: "Data Analysis",        desc: "Processes patterns and extracts actionable insights" },
  { key: "sentinel",  name: "Sentinel",  role: "Security",             desc: "Reviews all actions for risk and threat assessment" },
  { key: "steward",   name: "Steward",   role: "Resource Management",  desc: "Optimizes and manages operational system resources" },
  { key: "link",      name: "Link",      role: "Integration",          desc: "Interfaces with external APIs and data services" },
  { key: "keeper",    name: "Keeper",    role: "Memory",               desc: "Persists knowledge across operational cycles" },
  { key: "echo",      name: "Echo",      role: "Communication",        desc: "Synthesizes and delivers final responses" },
  { key: "pilot",     name: "Pilot",     role: "Task Coordination",    desc: "Manages execution queue and agent deployment" },
];

const BOOT_LOG = [
  "> INITIALIZING R.A.M.B.O NEURAL CORE...",
  "> LOADING AGENT PROFILES............. [10/10]",
  "> VERIFYING CRYPTOGRAPHIC KEYS......... OK",
  "> CALIBRATING THREAT MATRIX........... OK",
  "> ESTABLISHING OVERSEER UPLINK........ OK",
  "> AGENT NETWORK STATUS............. SCANNING",
  "> CLEARANCE LEVEL................. AUTHORIZED",
  "> ALL SYSTEMS NOMINAL. LAUNCHING.",
];

// Phase 1 sequential scan steps — each fills to 100% before advancing
const SCAN_STEPS = [
  "SCANNING NEURAL PATHWAYS",
  "SCANNING AGENT NETWORK",
  "SCANNING CRYPTOGRAPHIC KEYS",
];

const STATUS_COLORS = {
  online:  "#00ff88",
  working: "#e8b15a",
  idle:    "#8fa0b5", // lightened from #4a5568 for readable contrast on dark bg
  offline: "#5a6575", // lightened from #2a3040 so OFFLINE text is legible
};

const STATUS_LABELS = {
  online:  "ONLINE",
  working: "WORKING",
  idle:    "IDLE",
  offline: "OFFLINE",
};

/* ------------------------------------------------------------------ */
/*  HOOKS                                                               */
/* ------------------------------------------------------------------ */

const API = "http://localhost:8000";
const WS_URL = "ws://localhost:8000/ws/activity";

// True when the user has asked the OS to reduce motion.
function prefersReducedMotion() {
  return typeof window !== "undefined"
    && window.matchMedia
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

const IS_MOBILE = typeof window !== "undefined" && window.innerWidth < 768;

// Apply a live "STATUS:<name>:<state>" WebSocket update onto polled status data.
function applyLiveStatus(prev, name, state) {
  if (!prev) return prev;
  if (name === "rambo" || name === "overseer") {
    return { ...prev, overseer: { ...prev.overseer, status: state } };
  }
  return {
    ...prev,
    agents: (prev.agents || []).map(a =>
      a.name.toLowerCase() === name ? { ...a, status: state } : a),
  };
}

// One hook for the whole live backend link: REST polling (agent status +
// system stats) plus the WebSocket activity feed and live status overrides.
function useRamboLive() {
  const [statusData, setStatusData] = useState(null);
  const [stats,      setStats]      = useState(null);
  const [activity,   setActivity]   = useState([]);
  const [connected,  setConnected]  = useState(false);

  // REST polling
  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const r = await fetch(`${API}/agents/status`);
        if (r.ok && !cancelled) setStatusData(await r.json());
      } catch {}
      try {
        const r = await fetch(`${API}/system/stats`);
        if (r.ok && !cancelled) setStats(await r.json());
      } catch {}
    };
    poll();
    const id = setInterval(poll, 2000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  // WebSocket: live status + streaming activity log (auto-reconnect)
  useEffect(() => {
    let ws;
    let closed = false;
    let retry;
    const connect = () => {
      try { ws = new WebSocket(WS_URL); } catch { return; }
      ws.onopen  = () => setConnected(true);
      ws.onclose = () => { setConnected(false); if (!closed) retry = setTimeout(connect, 2500); };
      ws.onerror = () => { try { ws.close(); } catch {} };
      ws.onmessage = (e) => {
        const msg = String(e.data);
        const m = /^STATUS:([a-zA-Z]+):([a-zA-Z]+)$/.exec(msg);
        if (m) {
          setStatusData(prev => applyLiveStatus(prev, m[1].toLowerCase(), m[2].toLowerCase()));
          return;
        }
        // Log line — show it, and if it reports a completion, return that agent
        // to idle ("[Architect] Finished: …" / "[Echo] Response ready.").
        const fin = /^\[([a-zA-Z]+)\]\s+(?:Finished|Response ready)/.exec(msg);
        if (fin) {
          setStatusData(prev => applyLiveStatus(prev, fin[1].toLowerCase(), "idle"));
        }
        setActivity(prev => [...prev, { id: `${Date.now()}-${Math.random()}`, msg }].slice(-120));
      };
    };
    connect();
    return () => { closed = true; clearTimeout(retry); if (ws) try { ws.close(); } catch {} };
  }, []);

  return { statusData, stats, activity, connected };
}

// Typewriter that waits `startMs` before typing `text` one char at a time.
// Re-runs on mount, so the whole cascade restarts when the console appears.
// Honors prefers-reduced-motion by revealing the full text immediately.
function useDelayedTypewriter(text, speed, startMs) {
  const [out, setOut] = useState("");
  useEffect(() => {
    if (prefersReducedMotion()) { setOut(text); return; }
    setOut("");
    let i = 0;
    let intId;
    const startTimer = setTimeout(() => {
      intId = setInterval(() => {
        i += 1;
        setOut(text.slice(0, i));
        if (text[i - 1] && text[i - 1] !== " ") playKeyClick(); // click per keystroke
        if (i >= text.length) clearInterval(intId);
      }, speed);
    }, Math.max(0, startMs));
    return () => { clearTimeout(startTimer); clearInterval(intId); };
  }, [text, speed, startMs]);
  return out;
}

// Flips true once `startMs` has elapsed — used to fade a row in.
function useRevealAt(startMs) {
  const [on, setOn] = useState(false);
  useEffect(() => {
    if (prefersReducedMotion()) { setOn(true); return; }
    const t = setTimeout(() => setOn(true), Math.max(0, startMs));
    return () => clearTimeout(t);
  }, [startMs]);
  return on;
}

// Live clock format (module-level so the topbar typewriter effect can snapshot
// a fresh value the moment it starts typing).
function clockFmt() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

// Sequenced reveal timeline. Items type in reading order across four sections:
// topbar → roster → params → center. The whole cascade waits INITIAL_DELAY so
// the panels' settle animation (glitch-in) finishes first, with a longer pause
// between sections than between rows within a section.
const CHAR_SPEED    = 20;   // ms per character (still slower than the original 15)
const ITEM_GAP      = 70;   // ms between items within a section
const SECTION_GAP   = 340;  // ms between sections
const INITIAL_DELAY = 1100; // ms — let glitch-in settle (~1s) before typing starts

function buildReveal({ brandText, clockText, headline, agentNames, paramKeys, centerLines }) {
  let t = INITIAL_DELAY;
  const section = (items, leadingGap) => {
    t += leadingGap;
    return items.map((s) => {
      const start = t;
      t += s.length * CHAR_SPEED + ITEM_GAP;
      return start;
    });
  };
  const topbar = section([brandText, clockText], 0);
  const roster = section([headline, ...agentNames], SECTION_GAP);
  const params = section(paramKeys, SECTION_GAP);
  const center = section(centerLines, SECTION_GAP);
  return {
    speed:      CHAR_SPEED,
    brandAt:    topbar[0],
    clockAt:    topbar[1],
    headlineAt: roster[0],
    agentsAt:   roster.slice(1),
    paramsAt:   params,
    centerAt:   center,
  };
}

// System-parameter rows (keys are typed; values fade in alongside).
const PARAM_KEYS = [
  "DESIGNATION", "VERSION", "CLEARANCE", "BACKEND", "PROTOCOL",
  "AGENTS", "OVERSEER", "TIMEZONE", "BUILD", "OPERATOR",
];
function paramValues(overseerStatus) {
  return {
    DESIGNATION: "R.A.M.B.O",
    VERSION:     "VERSION III",
    CLEARANCE:   "AUTHORIZED",
    BACKEND:     "localhost:8000",
    PROTOCOL:    "HTTP / WebSocket",
    AGENTS:      `${AGENT_ROSTER.length} REGISTERED`,
    OVERSEER:    STATUS_LABELS[overseerStatus] ?? "OFFLINE",
    TIMEZONE:    "America/Detroit",
    BUILD:       "DEVELOPMENT",
    OPERATOR:    "DANIEL",
  };
}

const CENTER_SUBTITLE = "Responsive Autonomous Multi-Brain Operator";

/* ------------------------------------------------------------------ */
/*  SHARED PRIMITIVES                                                   */
/* ------------------------------------------------------------------ */

function AgentDot({ status }) {
  return (
    <span className="agent-dot" style={{ background: STATUS_COLORS[status] ?? STATUS_COLORS.offline }} />
  );
}

// Generic typewriter span — types `text` at `startMs`, shows a caret until done.
function Typed({ text, speed, startMs, className }) {
  const out = useDelayedTypewriter(text, speed, startMs);
  return (
    <span className={className}>
      {out}
      {out !== text && <span className="type-caret">▌</span>}
    </span>
  );
}

// Topbar clock — types a FRESH snapshot when it starts (not a stale mount value),
// then hands off to the live ticking value.
function TopbarClock({ liveValue, startMs, speed }) {
  const [typed, setTyped] = useState("");
  const [done, setDone]   = useState(false);
  useEffect(() => {
    if (prefersReducedMotion()) { setDone(true); return; }
    let i = 0;
    let intId;
    const startTimer = setTimeout(() => {
      const text = clockFmt(); // fresh snapshot at start
      intId = setInterval(() => {
        i += 1;
        setTyped(text.slice(0, i));
        if (text[i - 1] && text[i - 1] !== " ") playKeyClick();
        if (i >= text.length) { clearInterval(intId); setDone(true); }
      }, speed);
    }, Math.max(0, startMs));
    return () => { clearTimeout(startTimer); clearInterval(intId); };
  }, [startMs, speed]);

  return (
    <span className="topbar-time neon-clock">
      {done ? liveValue : typed}
      {!done && typed && <span className="type-caret">▌</span>}
    </span>
  );
}

// Topbar — brand + tabs (left) and clock (right) all type in after settle.
function Topbar({ brandText, clockStr, startBrand, startClock, speed }) {
  const tabsOn = useRevealAt(startBrand + brandText.length * speed + 140);
  return (
    <header className="splash-topbar glitch-in">
      <div className="topbar-left">
        <Typed className="brand-mark neon-brand" text={brandText} speed={speed} startMs={startBrand} />
        <span className={`topbar-tabs${tabsOn ? " revealed" : ""}`}>
          <span className="topbar-divider" />
          <span className="topbar-tab">SYSTEM</span>
          <span className="topbar-tab">LOGS</span>
        </span>
      </div>
      <div className="topbar-right">
        <TopbarClock liveValue={clockStr} startMs={startClock} speed={speed} />
      </div>
    </header>
  );
}

// Sound on/off toggle (also doubles as the "enable audio" gesture). Persists.
function SoundToggle() {
  const [muted, setMutedState] = useState(isMuted());
  const toggle = () => {
    resumeAudio();                 // the click is a user gesture → unlocks audio
    setMutedState(setMuted(!muted));
  };
  return (
    <button className="sound-toggle" type="button" onClick={toggle}
      aria-label={muted ? "Unmute audio" : "Mute audio"}
      title={muted ? "Sound off — click to enable" : "Sound on"}>
      {muted ? "🔇" : "🔊"}
    </button>
  );
}

// Phase 1 intro: a swirling magenta vortex that fills the screen while the HUD
// intro sound plays, then fades to reveal the booting screen. Duration is taken
// from the sound (~11s); calls onDone when finished.
function Vortex({ onDone }) {
  const [dur, setDur]   = useState(11);
  const [done, setDone] = useState(false);
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  useEffect(() => {
    if (prefersReducedMotion()) { setDone(true); onDoneRef.current && onDoneRef.current(); return; }
    const a = loadIntro();
    const onMeta = () => {
      const d = a.duration;
      if (d && isFinite(d)) setDur(Math.min(15, Math.max(3, d)));
    };
    if (a.duration && isFinite(a.duration)) onMeta();
    else a.addEventListener("loadedmetadata", onMeta, { once: true });
    playIntro();                   // gesture permitting
    return () => a.removeEventListener("loadedmetadata", onMeta);
  }, []);

  useEffect(() => {
    if (done) return undefined;
    const t = setTimeout(() => {
      setDone(true);
      onDoneRef.current && onDoneRef.current();
    }, dur * 1000);
    return () => clearTimeout(t);
  }, [dur, done]);

  if (done) return null;
  return (
    <div className="vortex" style={{ "--vdur": `${dur}s` }}>
      <div className="vortex-swirl" />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  PHASE 1 — TRANSMISSION SCREEN                                       */
/* ------------------------------------------------------------------ */

// A single boot-log line that types in (char by char, with key clicks) once
// its start time is reached.
function BootLine({ text, speed, startMs }) {
  const shown = useRevealAt(startMs);
  const typed = useDelayedTypewriter(text, speed, startMs);
  if (!shown) return null;
  const done = typed === text;
  return (
    <div className="tx-boot-line">
      {typed}{!done && <span className="tx-boot-cursor">█</span>}
    </div>
  );
}

const BOOT_SPEED = 14; // ms/char for the boot log

// Precomputed start offsets for the boot log (relative to when loading begins).
const BOOT_STARTS = (() => {
  let t = 0;
  return BOOT_LOG.map((l) => { const s = t; t += l.length * BOOT_SPEED + 180; return s; });
})();
const BOOT_TOTAL_MS = (() => {
  if (!BOOT_LOG.length) return 0;
  const last = BOOT_LOG.length - 1;
  return BOOT_STARTS[last] + BOOT_LOG[last].length * BOOT_SPEED + 180;
})();

function TransmissionScreen({ onAdvance }) {
  const [introDone,   setIntroDone]   = useState(false); // vortex finished
  const [loadStarted, setLoadStarted] = useState(false); // %bar + boot log begin
  const [progress,    setProgress]    = useState(0);
  const [connected,   setConnected]   = useState(false); // "CONNECTION ESTABLISHED"
  const onAdvanceRef = useRef(onAdvance);
  onAdvanceRef.current = onAdvance;

  // After the vortex: a beat, then start the %bar + boot-log typewriter.
  useEffect(() => {
    if (!introDone) return undefined;
    const t = setTimeout(() => setLoadStarted(true), 800);
    return () => clearTimeout(t);
  }, [introDone]);

  // Scan bar fills while the boot log types.
  useEffect(() => {
    if (!loadStarted) return undefined;
    const start = Date.now();
    const SCAN_DURATION = Math.max(2600, BOOT_TOTAL_MS);
    const id = setInterval(() => {
      const pct = Math.min(100, ((Date.now() - start) / SCAN_DURATION) * 100);
      setProgress(pct);
      if (pct >= 100) clearInterval(id);
    }, 30);
    return () => clearInterval(id);
  }, [loadStarted]);

  // When the boot log finishes: show "CONNECTION ESTABLISHED", then advance.
  useEffect(() => {
    if (!loadStarted) return undefined;
    const t1 = setTimeout(() => setConnected(true), BOOT_TOTAL_MS + 200);
    const t2 = setTimeout(() => onAdvanceRef.current(), BOOT_TOTAL_MS + 1900);
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, [loadStarted]);

  const scanLabel = progress < 40 ? SCAN_STEPS[0] : progress < 75 ? SCAN_STEPS[1] : SCAN_STEPS[2];

  return (
    <div className="phase-screen tx-screen">
      {/* Full-screen orb — identical size/look to Phase 2 */}
      <div className="orb-canvas">
        <Canvas camera={{ position: [0, 0, 4.2], fov: 45 }} gl={{ antialias: true, alpha: true }}>
          <RamboOrb3D />
          <EffectComposer>
            <Bloom luminanceThreshold={0.15} luminanceSmoothing={0.9}
              intensity={1.4} mipmapBlur radius={0.8} />
            <ChromaticAberration offset={new Vector2(0.0012, 0.0012)}
              radialModulation={false} modulationOffset={0} />
          </EffectComposer>
        </Canvas>
      </div>

      {/* Upper text appears only after the vortex finishes */}
      {introDone && (
        <div className="tx-content tx-content-overlay tx-fade-in">
          <div className="tx-emblem-title">R.A.M.B.O</div>
          <div className="tx-emblem-operator">RESPONSIVE AUTONOMOUS MULTI-BRAIN OPERATOR</div>

          <p className="tx-label">[ R.A.M.B.O SYSTEM ]</p>
          <p className="tx-subtitle">STANDBY FOR NEURAL SYNC</p>

          <div className="tx-status">
            <span className="tx-status-dot" />
            <span className="tx-status-text">BOOTING UP</span>
          </div>

          {/* %bar + boot log type in only after the upper text has loaded */}
          {loadStarted && (
            <>
              <div className="tx-scan-block">
                <p className="tx-scan-step">{scanLabel}</p>
                <div className="tx-progress-track">
                  <div className="tx-progress-fill" style={{ width: `${progress}%` }} />
                </div>
                <p className="tx-progress-label">{Math.floor(progress)}%</p>
              </div>

              <div className="tx-boot-log">
                {BOOT_LOG.map((line, i) => (
                  <BootLine key={i} text={line} speed={BOOT_SPEED} startMs={BOOT_STARTS[i]} />
                ))}
                {connected && (
                  <div className="tx-boot-line tx-connection-ok">&gt; CONNECTION ESTABLISHED</div>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {/* swirling magenta vortex intro — drives introDone when it finishes */}
      <Vortex onDone={() => setIntroDone(true)} />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  PHASE 2 — LEFT: AGENT ROSTER (names, roles, descriptions, status) */
/* ------------------------------------------------------------------ */

function RosterRow({ agent, status, startMs, speed }) {
  const revealed  = useRevealAt(startMs);
  const typedName = useDelayedTypewriter(agent.name, speed, startMs);
  const done = typedName === agent.name;
  return (
    <li className={`brief-agent-entry${revealed ? " revealed" : ""}`}>
      <div className="brief-agent-header">
        <AgentDot status={status} />
        <span className="brief-agent-name neon-agent">
          {typedName}{!done && <span className="type-caret">▌</span>}
        </span>
        {done && (
          <>
            <span className="brief-agent-role">{agent.role}</span>
            <span className="brief-agent-badge neon-badge" style={{ color: STATUS_COLORS[status] }}>
              {STATUS_LABELS[status]}
            </span>
          </>
        )}
      </div>
      {done && <p className="brief-agent-desc">{agent.desc}</p>}
    </li>
  );
}

function AgentRosterPanel({ statusData, headline, headlineAt, agentsAt, speed }) {
  const agents   = statusData?.agents ?? AGENT_ROSTER.map(a => ({ name: a.name, status: "offline" }));
  const agentMap = Object.fromEntries(agents.map(a => [a.name.toLowerCase(), a.status]));
  const typed    = useDelayedTypewriter(headline, speed, headlineAt);

  return (
    <aside className="roster-panel glitch-in">
      <h1 className="headline system-online">
        {typed}
        {typed !== headline && <span className="type-caret">▌</span>}
      </h1>
      <div className="brief-section-label neon-label">AGENT ROSTER</div>
      <ul className="brief-agent-list">
        {AGENT_ROSTER.map((a, i) => (
          <RosterRow key={a.key} agent={a} status={agentMap[a.key] ?? "offline"}
            startMs={agentsAt[i]} speed={speed} />
        ))}
      </ul>
    </aside>
  );
}

/* ------------------------------------------------------------------ */
/*  PHASE 2 — RIGHT: SYSTEM PARAMETERS                                 */
/* ------------------------------------------------------------------ */

function ParamRow({ paramKey, value, startMs, speed }) {
  const revealed = useRevealAt(startMs);
  const typedKey = useDelayedTypewriter(paramKey, speed, startMs);
  const done = typedKey === paramKey;
  return (
    <div className={`brief-param-row${revealed ? " revealed" : ""}`}>
      <span className="brief-param-key">
        {typedKey}{!done && <span className="type-caret">▌</span>}
      </span>
      {done && <span className="brief-param-val">{value}</span>}
    </div>
  );
}

function SystemParamsPanel({ statusData, paramsAt, speed }) {
  const overseer = statusData?.overseer ?? { status: "offline" };
  const values   = paramValues(overseer.status);

  return (
    <aside className="agent-panel glitch-in">
      <div className="agent-section-label neon-label">SYSTEM PARAMETERS</div>
      <div className="brief-params">
        {PARAM_KEYS.map((k, i) => (
          <ParamRow key={k} paramKey={k} value={values[k]} startMs={paramsAt[i]} speed={speed} />
        ))}
      </div>
    </aside>
  );
}

/* ------------------------------------------------------------------ */
/*  PHASE 2 — CENTER: ORB TITLE STACK (types in last)                 */
/* ------------------------------------------------------------------ */

function OrbTitleStack({ projectLabel, agentName, centerAt, speed }) {
  const p = useDelayedTypewriter(projectLabel, speed, centerAt[0]);
  const t = useDelayedTypewriter(agentName, speed, centerAt[1]);
  const s = useDelayedTypewriter(CENTER_SUBTITLE, speed, centerAt[2]);
  return (
    <div className="orb-title-stack">
      <div className="project-label">
        {p}{p !== projectLabel && p !== "" && <span className="type-caret">▌</span>}
      </div>
      <div className="title-banner">
        {t}{t !== agentName && t !== "" && <span className="type-caret">▌</span>}
      </div>
      <div className="subtitle">
        {s}{s !== CENTER_SUBTITLE && s !== "" && <span className="type-caret">▌</span>}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  PHASE 2 — COMMAND CONSOLE (live feed + directive input)           */
/* ------------------------------------------------------------------ */

function CommandConsole({ activity, connected }) {
  const [goal, setGoal] = useState("");
  const [busy, setBusy] = useState(false);
  const feedRef = useRef(null);

  // auto-scroll to newest line
  useEffect(() => {
    if (feedRef.current) feedRef.current.scrollTop = feedRef.current.scrollHeight;
  }, [activity]);

  const submit = async (e) => {
    e.preventDefault();
    const g = goal.trim();
    if (!g || busy) return;
    setBusy(true);
    try {
      await fetch(`${API}/rambo/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal: g }),
      });
      setGoal("");
    } catch {
      /* errors surface in the live feed */
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="cmd-console">
      <div className="cmd-feed" ref={feedRef} aria-live="polite">
        {activity.length === 0
          ? <div className="cmd-feed-empty">{"// awaiting activity…"}</div>
          : activity.map(a => <div key={a.id} className="cmd-feed-line">{a.msg}</div>)}
      </div>
      <form className="cmd-input-row" onSubmit={submit}>
        <span className={`cmd-conn ${connected ? "on" : "off"}`} aria-label={connected ? "Backend online" : "Backend offline"}>
          {connected ? "● LIVE" : "○ OFFLINE"}
        </span>
        <span className="cmd-prompt">&gt;</span>
        <input
          className="cmd-input"
          type="text"
          value={goal}
          onChange={e => setGoal(e.target.value)}
          placeholder="Issue a directive to R.A.M.B.O…"
          aria-label="Command input"
          spellCheck={false}
          autoComplete="off"
        />
        <button className="cmd-exec" type="submit" disabled={busy || !goal.trim()}>
          {busy ? "RUNNING…" : "EXECUTE"}
        </button>
      </form>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  STAT BAR                                                            */
/* ------------------------------------------------------------------ */

function StatBar({ label, value, max = 100, displayValue }) {
  const pct = Math.min(100, (value / max) * 100);
  return (
    <div className="stat-row">
      <span className="stat-label">{label}</span>
      <span className="stat-bar"><span className="stat-bar-fill" style={{ width: `${pct}%` }} /></span>
      <span className="stat-value">{displayValue ?? value}</span>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  ROOT — phase management                                             */
/* ------------------------------------------------------------------ */

export default function SplashScreen({
  projectLabel = "PROJECT: RAMBO",
  agentName    = "R.A.M.B.O",
  title        = "MK III",
  byline       = "BY DANIEL",
  headline     = "System Online",
}) {
  const [phase,  setPhase]  = useState("transmission");
  const [fading, setFading] = useState(false);

  // Stable across re-renders — polling/clock updates must NOT recreate these,
  // otherwise child phase timers restart and the scan bar loops forever.
  const advance = useCallback((next) => {
    setFading(true);
    setTimeout(() => { setPhase(next); setFading(false); }, 480);
  }, []);
  const goMain = useCallback(() => advance("main"), [advance]);

  // Live backend link: status + system stats + WebSocket activity feed.
  const { statusData, stats, activity, connected } = useRamboLive();

  // Real system stats → stat bars (falls back to em-dash when unavailable).
  const statBars = stats?.available
    ? [
        { label: "CPU", value: stats.cpu_percent,  displayValue: `${Math.round(stats.cpu_percent)}%` },
        { label: "RAM", value: stats.ram_percent,  displayValue: `${stats.ram_used_gb}G` },
        { label: "DSK", value: stats.disk_percent, displayValue: `${stats.disk_used_gb}G` },
      ]
    : [
        { label: "CPU", value: 0, displayValue: "—" },
        { label: "RAM", value: 0, displayValue: "—" },
        { label: "DSK", value: 0, displayValue: "—" },
      ];

  // Audio: browsers require a user gesture before sound can play, so rather than
  // firing the chime at the (gesture-less) auto-transition where it'd be lost,
  // we start the console audio at the FIRST moment it's both unlocked AND we're
  // on the console — whichever comes later.
  const phaseRef = useRef(phase);
  phaseRef.current = phase;
  const audioStartedRef = useRef(false);

  const startConsoleAudio = useCallback(() => {
    if (audioStartedRef.current) return;
    if (!audioRunning()) return;
    if (phaseRef.current !== "main") return;
    audioStartedRef.current = true;
    startHum();
  }, []);

  useEffect(() => {
    resumeAudio();           // best-effort (usually needs the gesture below)
    startConsoleAudio();
    const onGesture = () => { resumeAudio(); startConsoleAudio(); };
    const evs = ["pointerdown", "keydown", "touchstart", "click"];
    evs.forEach(ev => window.addEventListener(ev, onGesture));
    return () => evs.forEach(ev => window.removeEventListener(ev, onGesture));
  }, [startConsoleAudio]);

  // try again whenever we reach the console (covers the already-unlocked case)
  useEffect(() => {
    if (phase !== "main") return;
    startConsoleAudio();
    return () => stopHum();
  }, [phase, startConsoleAudio]);

  const [clockStr, setClockStr] = useState(clockFmt);
  useEffect(() => {
    const id = setInterval(() => setClockStr(clockFmt()), 1000); // tick seconds
    return () => clearInterval(id);
  }, []);

  const brandText = `${agentName} ${title.replace(" ", ".")}`;

  const mouseRef = useRef({ x: 0, y: 0 });
  useEffect(() => {
    const handler = (e) => {
      mouseRef.current = {
        x:  (e.clientX / window.innerWidth  - 0.5) * 2,
        y: -(e.clientY / window.innerHeight - 0.5) * 2,
      };
    };
    window.addEventListener("mousemove", handler);
    return () => window.removeEventListener("mousemove", handler);
  }, []);

  // Sequenced reveal timeline (values are stable across re-renders):
  // topbar → roster → params → center title, each starting after the previous.
  const reveal = buildReveal({
    brandText,
    clockText: "00:00:00 AM",
    headline,
    agentNames: AGENT_ROSTER.map(a => a.name),
    paramKeys: PARAM_KEYS,
    centerLines: [projectLabel, agentName, CENTER_SUBTITLE],
  });

  return (
    <div className={`splash-root${fading ? " phase-fading" : ""}`}>

      <SoundToggle />

      {phase === "transmission" && (
        <TransmissionScreen onAdvance={goMain} />
      )}

      {phase === "main" && (
        <>
          {/* full-screen orb (dpr + bloom tuned down on mobile) */}
          <div className="orb-canvas">
            <Canvas camera={{ position: [0, 0, 4.2], fov: 45 }}
              dpr={[1, IS_MOBILE ? 1.5 : 2]} gl={{ antialias: true, alpha: true }}>
              <RamboOrb3D mouseRef={mouseRef} />
              <EffectComposer>
                <Bloom luminanceThreshold={0.15} luminanceSmoothing={0.9}
                  intensity={1.4} mipmapBlur={!IS_MOBILE} radius={0.8} />
                <ChromaticAberration offset={new Vector2(0.0012, 0.0012)}
                  radialModulation={false} modulationOffset={0} />
              </EffectComposer>
            </Canvas>
          </div>

          <div className="splash-grid-overlay" />

          <Topbar brandText={brandText} clockStr={clockStr}
            startBrand={reveal.brandAt} startClock={reveal.clockAt} speed={reveal.speed} />

          <div className="byline">{byline}</div>

          {/* center title types in LAST, after roster + params */}
          <OrbTitleStack projectLabel={projectLabel} agentName={agentName}
            centerAt={reveal.centerAt} speed={reveal.speed} />

          <main className="splash-main">
            {/* LEFT: agent roster — types in FIRST, top-down */}
            <AgentRosterPanel statusData={statusData} headline={headline}
              headlineAt={reveal.headlineAt} agentsAt={reveal.agentsAt} speed={reveal.speed} />
            {/* RIGHT: system parameters — types in SECOND, top-down */}
            <SystemParamsPanel statusData={statusData}
              paramsAt={reveal.paramsAt} speed={reveal.speed} />
          </main>

          <footer className="splash-footer glitch-in">
            <div className="stat-panel">
              {statBars.map(s => <StatBar key={s.label} {...s} />)}
            </div>
            {/* functional command console replaces the decorative dock */}
            <CommandConsole activity={activity} connected={connected} />
          </footer>
        </>
      )}
    </div>
  );
}

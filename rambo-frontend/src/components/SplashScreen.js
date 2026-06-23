// SplashScreen.js
import React, { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { Canvas } from "@react-three/fiber";
import { EffectComposer, Bloom } from "@react-three/postprocessing";
import CosmicOrb from "./CosmicOrb";
import CosmicBackground from "./CosmicBackground";
import AgentConstellation from "./AgentConstellation";
import DispatchBeams from "./DispatchBeam";
import ProcessingHelix from "./ProcessingHelix";
import usePerformanceMode from "./usePerformanceMode";
import { useVoiceReactivity, CONV_STATES } from "./useVoiceReactivity";
import { VoiceControls } from "./VoiceControls";
import { StatBars, CostIndicator, useCostDashboard, FactoryDock, useFactoryPending, ConfirmationDock, HandoffDock, SoundGate } from "./SharedHUD";
import {
  resumeAudio, audioRunning, startHum, stopHum,
  loadIntro, playKeyClick,
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
  const [responses,  setResponses]  = useState({}); // { agentKey: responseText }
  const [dispatches, setDispatches] = useState([]);  // Tier 5: active dispatch beams
  const [processing, setProcessing] = useState(false); // Tier 5: helix active

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

        // Structured JSON messages: { t: "response"|"contact", agent, text }
        if (msg.charAt(0) === "{") {
          try {
            const j = JSON.parse(msg);
            if (j.t === "response" && j.agent) {
              setResponses(prev => ({ ...prev, [j.agent.toLowerCase()]: j.text }));
            }
            // contact is also surfaced via its companion log line below
          } catch { /* ignore malformed */ }
          return;
        }

        const m = /^STATUS:([a-zA-Z]+):([a-zA-Z]+)$/.exec(msg);
        if (m) {
          const agentName = m[1].toLowerCase();
          const newStatus = m[2].toLowerCase();
          setStatusData(prev => applyLiveStatus(prev, agentName, newStatus));
          if (newStatus === "working" || newStatus === "active") {
            setProcessing(true);
            setDispatches(prev => [...prev, {
              id: `${agentName}-${Date.now()}`,
              agentKey: agentName,
            }]);
          }
          return;
        }
        // Log line — show it, and if it reports a completion, return that agent
        // to idle ("[Architect] Finished: …" / "[Echo] Response ready.").
        const agentLog = /^\[([a-zA-Z]+)\]/.exec(msg);
        const fin = /^\[([a-zA-Z]+)\]\s+(?:Finished|Response ready)/.exec(msg);
        if (fin) {
          setStatusData(prev => applyLiveStatus(prev, fin[1].toLowerCase(), "idle"));
          setProcessing(false);
        } else if (agentLog) {
          const aName = agentLog[1].toLowerCase();
          setDispatches(prev => {
            if (prev.some(d => d.agentKey === aName)) return prev;
            return [...prev, { id: `${aName}-${Date.now()}`, agentKey: aName }];
          });
          setProcessing(true);
        }
        setActivity(prev => [...prev, { id: `${Date.now()}-${Math.random()}`, msg }].slice(-120));
      };
    };
    connect();
    return () => { closed = true; clearTimeout(retry); if (ws) try { ws.close(); } catch {} };
  }, []);

  const dismissResponse = useCallback((agentKey) => {
    setResponses(prev => {
      const next = { ...prev };
      delete next[agentKey];
      return next;
    });
  }, []);

  const dismissBeam = useCallback((beamId) => {
    setDispatches(prev => prev.filter(d => d.id !== beamId));
  }, []);

  return { statusData, stats, activity, connected, responses, dismissResponse,
           dispatches, processing, dismissBeam };
}

// Typewriter that waits `startMs` before typing `text` one char at a time.
// Re-runs on mount, so the whole cascade restarts when the console appears.
// Honors prefers-reduced-motion by revealing the full text immediately.
function useDelayedTypewriter(text, speed, startMs, silent = false) {
  const [out, setOut] = useState(speed === 0 ? text : "");
  useEffect(() => {
    if (speed === 0 || prefersReducedMotion()) { setOut(text); return; }
    setOut("");
    let i = 0;
    let intId;
    const startTimer = setTimeout(() => {
      intId = setInterval(() => {
        i += 1;
        setOut(text.slice(0, i));
        if (!silent && text[i - 1] && text[i - 1] !== " ") playKeyClick();
        if (i >= text.length) clearInterval(intId);
      }, speed);
    }, Math.max(0, startMs));
    return () => { clearTimeout(startTimer); clearInterval(intId); };
  }, [text, speed, startMs, silent]);
  return out;
}

// Flips true once `startMs` has elapsed — used to fade a row in.
function useRevealAt(startMs) {
  const [on, setOn] = useState(startMs === 0);
  useEffect(() => {
    if (startMs === 0 || prefersReducedMotion()) { setOn(true); return; }
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
    <span
      className={`agent-dot${status === "working" ? " working" : ""}`}
      style={{ background: STATUS_COLORS[status] ?? STATUS_COLORS.offline }}
    />
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
function dateFmt() {
  return new Date().toLocaleDateString("en-US", { month: "2-digit", day: "2-digit", year: "numeric" });
}

function Topbar({ brandText, clockStr, startBrand, startClock, speed, onCouncil }) {
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
        <span className="topbar-council" onClick={onCouncil}>◆ COUNCIL VIEW</span>
        <span className="topbar-date">{dateFmt()}</span>
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

// Lightspeed warp — gold star streaks accelerating outward from the centre,
// like jumping to hyperspace. Fades out when told to close.
function Warp({ closing }) {
  const ref = useRef();
  useEffect(() => {
    if (prefersReducedMotion()) return undefined;
    const canvas = ref.current;
    if (!canvas) return undefined;
    const ctx = canvas.getContext("2d");
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let w, h, cx, cy;
    const resize = () => {
      w = canvas.width = Math.floor(window.innerWidth * dpr);
      h = canvas.height = Math.floor(window.innerHeight * dpr);
      cx = w / 2; cy = h / 2;
    };
    resize();
    window.addEventListener("resize", resize);

    const N = 340;
    const reset = (s) => { s.x = Math.random() * 2 - 1; s.y = Math.random() * 2 - 1; s.z = 1; s.pz = 1; };
    const stars = Array.from({ length: N }, () => { const s = {}; reset(s); s.z = Math.random(); s.pz = s.z; return s; });

    const t0 = performance.now();
    let raf;
    const draw = (now) => {
      const elapsed = (now - t0) / 1000;
      const speed = 0.006 + Math.min(0.055, elapsed * 0.012); // ramps up → lightspeed
      const scale = Math.min(w, h) * 0.7;

      ctx.fillStyle = "rgba(8, 9, 11, 0.32)"; // trail fade
      ctx.fillRect(0, 0, w, h);

      for (const s of stars) {
        s.pz = s.z;
        s.z -= speed;
        if (s.z <= 0.012) reset(s);
        const sx = cx + (s.x / s.z) * scale;
        const sy = cy + (s.y / s.z) * scale;
        const px = cx + (s.x / s.pz) * scale;
        const py = cy + (s.y / s.pz) * scale;
        const k = 1 - s.z;
        ctx.strokeStyle = `rgba(${232 + k * 23}, ${177 + k * 40}, ${90 + k * 48}, ${Math.min(1, k * 1.3)})`;
        ctx.lineWidth = Math.max(0.6, k * 2.6) * dpr;
        ctx.beginPath();
        ctx.moveTo(px, py);
        ctx.lineTo(sx, sy);
        ctx.stroke();
      }
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);

    return () => { cancelAnimationFrame(raf); window.removeEventListener("resize", resize); };
  }, []);

  return <canvas ref={ref} className={`warp${closing ? " warp-closing" : ""}`} />;
}

/* ------------------------------------------------------------------ */
/*  PHASE 1 — TRANSMISSION SCREEN                                       */
/* ------------------------------------------------------------------ */

// A single boot-log line that types in (char by char) once its start is reached.
function BootLine({ text, speed, startMs, silent }) {
  const shown = useRevealAt(startMs);
  const typed = useDelayedTypewriter(text, speed, startMs, silent);
  if (!shown) return null;
  const done = typed === text;
  return (
    <div className="tx-boot-line">
      {typed}{!done && <span className="tx-boot-cursor">█</span>}
    </div>
  );
}

const BOOT_TYPE_SPEED = 12; // ms/char for the boot log (silent in Phase 1)

function TransmissionScreen({ onAdvance }) {
  const [introDone,   setIntroDone]   = useState(false); // warp begins clearing
  const [warpGone,    setWarpGone]    = useState(false); // warp removed
  const [loadStarted, setLoadStarted] = useState(false); // %bar + boot log begin
  const [progress,    setProgress]    = useState(0);
  const [nowBooting,  setNowBooting]  = useState(false); // "NOW BOOTING UP"
  const [connected,   setConnected]   = useState(false); // "CONNECTION ESTABLISHED"
  const [lineGap,     setLineGap]     = useState(520);    // ms between boot lines
  const [scanDur,     setScanDur]     = useState(4200);
  const onAdvanceRef = useRef(onAdvance);
  onAdvanceRef.current = onAdvance;

  // The whole Phase 1 is synced to the intro sound: the warp + boot sequence
  // span its length. We attempt autoplay, retry on the first user gesture, and
  // fall back after a few seconds so it never gets stuck. The transition waits
  // for "CONNECTION ESTABLISHED" to be readable (≈1.9s) before advancing.
  useEffect(() => {
    const a = loadIntro();
    let durMs = 11000;
    let started = false;
    const timers = [];

    const startTimeline = () => {
      if (started) return;
      started = true;

      const introAt = durMs * 0.42;
      const loadAt  = durMs * 0.47;
      const bootWin = durMs * 0.36;
      const gap = Math.max(320, bootWin / BOOT_LOG.length);
      setLineGap(gap);
      setScanDur(gap * BOOT_LOG.length);

      const connectedAt = durMs * 0.88;
      timers.push(setTimeout(() => setIntroDone(true),  introAt));
      timers.push(setTimeout(() => setWarpGone(true),   introAt + 750));
      timers.push(setTimeout(() => setLoadStarted(true), loadAt));
      timers.push(setTimeout(() => setNowBooting(true), durMs * 0.84));
      timers.push(setTimeout(() => setConnected(true),  connectedAt));
      // hold so "CONNECTION ESTABLISHED" is fully shown before we transition
      timers.push(setTimeout(() => onAdvanceRef.current(), connectedAt + 1900));
    };

    const onMeta = () => { if (a.duration && isFinite(a.duration)) durMs = a.duration * 1000; };
    if (a.duration && isFinite(a.duration)) onMeta();
    else a.addEventListener("loadedmetadata", onMeta, { once: true });

    const onPlay = () => startTimeline();
    a.addEventListener("play", onPlay);

    const tryPlay = () => {
      resumeAudio();
      try { a.currentTime = 0; const p = a.play(); if (p) p.catch(() => {}); } catch { /* ignore */ }
    };
    tryPlay();                                   // autoplay attempt
    const onGesture = () => tryPlay();           // retry on first interaction
    const evs = ["pointerdown", "keydown", "touchstart", "click"];
    evs.forEach(ev => window.addEventListener(ev, onGesture, { once: true }));

    const fallback = setTimeout(startTimeline, 4500); // run silently if still blocked

    return () => {
      timers.forEach(clearTimeout);
      clearTimeout(fallback);
      a.removeEventListener("loadedmetadata", onMeta);
      a.removeEventListener("play", onPlay);
      evs.forEach(ev => window.removeEventListener(ev, onGesture));
      try { a.pause(); } catch { /* ignore */ }
    };
  }, []);

  // Scan bar fills across the boot window.
  useEffect(() => {
    if (!loadStarted) return undefined;
    const start = Date.now();
    const id = setInterval(() => {
      const pct = Math.min(100, ((Date.now() - start) / scanDur) * 100);
      setProgress(pct);
      if (pct >= 100) clearInterval(id);
    }, 30);
    return () => clearInterval(id);
  }, [loadStarted, scanDur]);

  const scanLabel = progress < 40 ? SCAN_STEPS[0] : progress < 75 ? SCAN_STEPS[1] : SCAN_STEPS[2];

  return (
    <div className="phase-screen tx-screen">
      {/* Full-screen cosmic orb — same wireframe icosahedron as Phase 2 */}
      <div className="orb-canvas">
        <Canvas camera={{ position: [0, 0, 4.2], fov: 45 }} gl={{ antialias: true, alpha: true, premultipliedAlpha: false, powerPreference: 'high-performance', stencil: false }}>
          <CosmicBackground />
          <CosmicOrb />
          <EffectComposer>
            <Bloom luminanceThreshold={0.7} luminanceSmoothing={0.95}
              intensity={0.6} mipmapBlur radius={0.5} />
          </EffectComposer>
        </Canvas>
      </div>

      {/* Upper text appears once the vortex starts clearing */}
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
                  <BootLine key={i} text={line} speed={BOOT_TYPE_SPEED} startMs={i * lineGap} silent />
                ))}
                {nowBooting && (
                  <div className="tx-boot-line tx-now-booting">&gt; NOW BOOTING UP</div>
                )}
                {connected && (
                  <div className="tx-boot-line tx-connection-ok">&gt; CONNECTION ESTABLISHED</div>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {/* lightspeed warp — runs until the timeline tells it to clear */}
      {!warpGone && <Warp closing={introDone} />}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  PHASE 2 — LEFT: AGENT ROSTER (names, roles, descriptions, status) */
/* ------------------------------------------------------------------ */

function RosterRow({ agent, status, startMs, speed, response, rowRef, onClick, onDismissResponse }) {
  const revealed  = useRevealAt(startMs);
  const typedName = useDelayedTypewriter(agent.name, speed, startMs);
  const done = typedName === agent.name;
  const [minimized, setMinimized] = useState(false);
  return (
    <li
      className={`brief-agent-entry agent-clickable${revealed ? " revealed" : ""}`}
      ref={(el) => rowRef && rowRef(agent.key, el)}
      onClick={() => onClick && onClick(agent)}
      title={`${agent.name} — click for details`}
    >
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
      {done && response && (
        <div className="agent-response" onClick={(e) => e.stopPropagation()}>
          <div className="agent-response-arm" />
          <div className="agent-response-body">
            <div className="agent-response-head">
              <span>{agent.name} · RESPONSE</span>
              <span className="agent-response-controls">
                <button className="agent-response-btn" onClick={(e) => { e.stopPropagation(); setMinimized(m => !m); }}
                  title={minimized ? "Expand" : "Minimize"} aria-label={minimized ? "Expand" : "Minimize"}>
                  {minimized ? "▪" : "▬"}
                </button>
                <button className="agent-response-btn" onClick={(e) => { e.stopPropagation(); onDismissResponse && onDismissResponse(agent.key); }}
                  title="Dismiss" aria-label="Dismiss">✕</button>
              </span>
            </div>
            {!minimized && <div className="agent-response-text">{response}</div>}
          </div>
        </div>
      )}
    </li>
  );
}

function AgentRosterPanel({ statusData, headline, headlineAt, agentsAt, speed, responses = {}, rowRef, onAgentClick, onDismissResponse, onNavigate }) {
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
            startMs={agentsAt[i]} speed={speed} response={responses[a.key]}
            rowRef={rowRef} onClick={onAgentClick} onDismissResponse={onDismissResponse} />
        ))}
      </ul>
      <div className="brief-section-label neon-label systems-label">SYSTEMS</div>
      <ul className="systems-nav">
        <li className="systems-nav-item" onClick={() => onNavigate && onNavigate("/learning")}>
          <span className="systems-nav-icon">🧬</span>
          <span className="systems-nav-text">Learning Log</span>
        </li>
        <li className="systems-nav-item" onClick={() => onNavigate && onNavigate("/council")}>
          <span className="systems-nav-icon">◆</span>
          <span className="systems-nav-text">Round Table</span>
        </li>
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
/*  PHASE 2 — EM PULSES (small circular ripples, like cells firing)   */
/* ------------------------------------------------------------------ */

function OrbWeb() {
  const points = useMemo(() => {
    let seed = 1337;
    const rand = () => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; };
    const N = 60;
    return Array.from({ length: N }, () => {
      const bright = rand() > 0.7;
      return {
        x: 2 + rand() * 96,
        y: 4 + rand() * 92,
        bright,
        coreR: (2.5 + rand() * 3).toFixed(1),       // px
        ringScale: (5 + rand() * 8).toFixed(1),     // how far the ripple grows
        ringDur: (2.2 + rand() * 2.8).toFixed(2),
        ringDelay: (rand() * 4).toFixed(2),
        twoRings: rand() > 0.5,
        coreDur: (1.6 + rand() * 1.8).toFixed(2),
        coreDelay: (-rand() * 3).toFixed(2),
      };
    });
  }, []);

  return (
    <div className="orb-web">
      {points.map((p, i) => {
        const color = p.bright ? "var(--accent-glow)" : "var(--accent)";
        return (
          <div key={i} className="emp" style={{ left: `${p.x}%`, top: `${p.y}%`, color }}>
            <span className="emp-ring"
              style={{ "--rs": p.ringScale, animationDuration: `${p.ringDur}s`, animationDelay: `${p.ringDelay}s` }} />
            {p.twoRings && (
              <span className="emp-ring"
                style={{ "--rs": p.ringScale, animationDuration: `${p.ringDur}s`,
                  animationDelay: `${(Number(p.ringDelay) + Number(p.ringDur) / 2).toFixed(2)}s` }} />
            )}
            <span className="emp-core"
              style={{ width: `${p.coreR}px`, height: `${p.coreR}px`,
                "--cop": p.bright ? 0.9 : 0.55, animationDuration: `${p.coreDur}s`, animationDelay: `${p.coreDelay}s` }} />
          </div>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  PHASE 2 — COMMAND CONSOLE (live feed + directive input)           */
/* ------------------------------------------------------------------ */

function ActivityFeed({ activity }) {
  const feedRef = useRef(null);
  useEffect(() => {
    if (feedRef.current) feedRef.current.scrollTop = feedRef.current.scrollHeight;
  }, [activity]);
  return (
    <div className="activity-feed" ref={feedRef} aria-live="polite">
      <div className="activity-feed-label">◆ ACTIVITY FEED</div>
      {activity.length === 0
        ? <div className="cmd-feed-empty">{"// awaiting activity…"}</div>
        : activity.map(a => <div key={a.id} className="cmd-feed-line">{a.msg}</div>)}
    </div>
  );
}

function CommandConsole({ connected, onResult, voiceText, voiceState, onVoiceExecuted }) {
  const [goal, setGoal] = useState("");
  const [busy, setBusy] = useState(false);
  const locRef = useRef({ lat: null, lon: null });
  const voiceSubmitTimer = useRef(null);

  useEffect(() => {
    if (voiceText && voiceState === "listening") {
      setGoal(voiceText);
    }
  }, [voiceText, voiceState]);

  useEffect(() => {
    if (voiceState === "processing" && goal.trim() && !busy) {
      voiceSubmitTimer.current = setTimeout(() => {
        submitGoal(goal.trim());
      }, 300);
    }
    return () => { if (voiceSubmitTimer.current) clearTimeout(voiceSubmitTimer.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [voiceState]);

  useEffect(() => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (pos) => { locRef.current = { lat: pos.coords.latitude, lon: pos.coords.longitude }; },
      () => {},
      { timeout: 8000, maximumAge: 600000 },
    );
  }, []);

  const submitGoal = async (g) => {
    if (!g || busy) return;
    setBusy(true);
    try {
      const res = await fetch(`${API}/rambo/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal: g, lat: locRef.current.lat, lon: locRef.current.lon }),
      });
      const data = await res.json().catch(() => ({}));
      const responseText = data.response || "(no response)";
      onResult({ goal: g, text: responseText, agent: (data.agent || "echo").toLowerCase() });
      setGoal("");
      if (onVoiceExecuted) onVoiceExecuted(responseText);
    } catch {
      onResult({ goal: g, text: "Request failed — is the backend running?", agent: "echo" });
    } finally {
      setBusy(false);
    }
  };

  const submit = (e) => {
    e.preventDefault();
    submitGoal(goal.trim());
  };

  return (
    <div className="cmd-console">
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

// Draggable response panel that branches (with a connector line) out from the
// agent that produced the final output.
function ResultBranch({ result, anchorEl, onClose }) {
  const [pos, setPos] = useState(null);
  const dragRef = useRef(null);

  // initial position: just to the right of the producing agent's row
  useEffect(() => {
    const r = anchorEl && anchorEl.getBoundingClientRect ? anchorEl.getBoundingClientRect() : null;
    if (r) {
      setPos({ x: Math.min(window.innerWidth - 400, r.right + 56), y: Math.max(16, r.top - 12) });
    } else {
      setPos({ x: Math.max(16, window.innerWidth / 2 - 190), y: window.innerHeight / 2 - 130 });
    }
  }, [anchorEl, result]);

  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const beginDrag = (e) => {
    if (!pos) return;
    const start = { mx: e.clientX, my: e.clientY, x: pos.x, y: pos.y };
    const move = (ev) => setPos({ x: start.x + (ev.clientX - start.mx), y: start.y + (ev.clientY - start.my) });
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    dragRef.current = up;
  };

  if (!pos) return null;
  const a = anchorEl && anchorEl.getBoundingClientRect ? anchorEl.getBoundingClientRect() : null;
  const start = a ? { x: a.right, y: a.top + a.height / 2 } : null;
  const end = { x: pos.x, y: pos.y + 22 };
  const label = result.agent ? result.agent.charAt(0).toUpperCase() + result.agent.slice(1) : "R.A.M.B.O";

  return (
    <>
      {start && (
        <svg className="branch-line" xmlns="http://www.w3.org/2000/svg">
          <path
            d={`M ${start.x} ${start.y} C ${(start.x + end.x) / 2} ${start.y}, ${(start.x + end.x) / 2} ${end.y}, ${end.x} ${end.y}`}
            fill="none" stroke="var(--teal)" strokeWidth="1.4" opacity="0.75"
            filter="url(#branchGlow)" />
          <defs>
            <filter id="branchGlow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="3" result="blur"/>
              <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
            </filter>
          </defs>
          <circle cx={start.x} cy={start.y} r="3" fill="var(--teal)" />
          <circle cx={end.x} cy={end.y} r="3" fill="var(--teal)" />
        </svg>
      )}
      <div className="branch-panel" style={{ left: pos.x, top: pos.y }}>
        <div className="branch-head" onPointerDown={beginDrag}>
          <span className="branch-title">{label} · RESPONSE</span>
          <button className="branch-close" type="button" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <div className="branch-goal">&gt; {result.goal}</div>
        <div className="branch-body">{result.text}</div>
      </div>
    </>
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
  skipIntro    = false,
}) {
  const [phase,  setPhase]  = useState(skipIntro ? "main" : "transmission");
  const [fading, setFading] = useState(false);

  // Tier 3: voice reactivity — wake word "Rambo" + TTS response
  const [voiceText, setVoiceText] = useState("");
  const voiceSetStateRef = useRef(null);
  const speakRef = useRef(null);
  const handleFinalTranscript = useCallback((text) => {
    setVoiceText(text);
    setTimeout(() => {
      if (voiceSetStateRef.current) voiceSetStateRef.current(CONV_STATES.PROCESSING);
    }, 800);
  }, []);
  const {
    levelRef: audioLevelRef, state: convState, setState: voiceSetState,
    micActive, toggleMic, startMic, speakResponse,
  } = useVoiceReactivity({
    onTranscript: setVoiceText,
    onFinalTranscript: handleFinalTranscript,
  });
  voiceSetStateRef.current = voiceSetState;
  speakRef.current = speakResponse;

  // Auto-start mic in IDLE mode when Phase 2 loads
  const micAutoStarted = useRef(false);
  useEffect(() => {
    if (phase === "main" && !micAutoStarted.current) {
      micAutoStarted.current = true;
      // Small delay to let the page settle before requesting mic
      setTimeout(() => { startMic(); }, 1200);
    }
  }, [phase, startMic]);

  const handleVoiceExecuted = useCallback((responseText) => {
    setVoiceText("");
    if (responseText && speakRef.current) {
      // Read the response, then ask if there's anything else
      speakRef.current(responseText, true); // true = conversational follow-up
    } else {
      if (voiceSetStateRef.current) voiceSetStateRef.current(CONV_STATES.IDLE);
    }
  }, []);

  // Result branch (response panel + connector) + clickable agents
  const [result, setResult] = useState(null);
  const agentRowsRef = useRef({});
  const registerRow = useCallback((key, el) => { agentRowsRef.current[key] = el; }, []);
  const nav = useNavigate();
  const onAgentClick = useCallback((agent) => {
    nav(`/agent/${agent.key}`);
  }, [nav]);

  // Stable across re-renders — polling/clock updates must NOT recreate these,
  // otherwise child phase timers restart and the scan bar loops forever.
  const advance = useCallback((next) => {
    setFading(true);
    setTimeout(() => { setPhase(next); setFading(false); }, 480);
  }, []);
  const goMain = useCallback(() => advance("main"), [advance]);

  // Live backend link: status + system stats + WebSocket activity feed.
  const { statusData, stats, activity, connected, responses, dismissResponse,
          dispatches, processing, dismissBeam } = useRamboLive();
  const perf = usePerformanceMode();
  const costData = useCostDashboard();
  const { pending: factoryPending, refresh: refreshFactory } = useFactoryPending();

  // Build status map for constellation: { architect: "active", scout: "idle", ... }
  const agentStatusMap = useMemo(() => {
    const map = {};
    if (statusData?.agents) {
      statusData.agents.forEach(a => {
        const key = (a.key || a.name || "").toLowerCase();
        map[key] = a.status || "idle";
      });
    }
    return map;
  }, [statusData]);

  const onNavigate = useCallback((path) => { nav(path); }, [nav]);

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
  // When skipIntro is true (Command Center click), skip the typing cascade entirely.
  const reveal = skipIntro
    ? { speed: 0, brandAt: 0, clockAt: 0, headlineAt: 0,
        agentsAt: AGENT_ROSTER.map(() => 0), paramsAt: PARAM_KEYS.map(() => 0),
        centerAt: [0, 0, 0] }
    : buildReveal({
        brandText,
        clockText: "00:00:00 AM",
        headline,
        agentNames: AGENT_ROSTER.map(a => a.name),
        paramKeys: PARAM_KEYS,
        centerLines: [projectLabel, agentName, CENTER_SUBTITLE],
      });

  return (
    <div className={`splash-root${fading ? " phase-fading" : ""}`}>

      {/* gold flash during the phase transition (on-theme, not a black cut) */}
      {fading && <div className="phase-flash" />}

      {phase === "main" && (
        <VoiceControls micActive={micActive} toggleMic={toggleMic} convState={convState} />
      )}

      {phase === "transmission" && (
        <TransmissionScreen onAdvance={goMain} />
      )}

      {phase === "main" && (
        <>
          {/* full-screen cosmic orb — wireframe icosahedron with fresnel glow */}
          <div className="orb-canvas">
            <Canvas camera={{ position: [0, 0, 4.2], fov: 45 }}
              dpr={perf.isLow ? [1, 1] : [1, IS_MOBILE ? 1.5 : 2]} gl={{ antialias: !perf.isLow, alpha: true, premultipliedAlpha: false, powerPreference: 'high-performance', stencil: false }}>
              <CosmicBackground />
              <CosmicOrb mouseRef={mouseRef} audioLevelRef={audioLevelRef} />
              <AgentConstellation statusMap={agentStatusMap} />
              <DispatchBeams dispatches={dispatches} onBeamComplete={dismissBeam} />
              <ProcessingHelix active={processing} />
              <EffectComposer enabled={perf.bloomEnabled}>
                <Bloom luminanceThreshold={0.7} luminanceSmoothing={0.95}
                  intensity={0.6} mipmapBlur={!IS_MOBILE} radius={0.5} />
              </EffectComposer>
            </Canvas>
          </div>

          {/* filament web radiating from the orb out to the UI zones */}
          <OrbWeb />

          <div className="splash-grid-overlay" />

          <Topbar brandText={brandText} clockStr={clockStr}
            startBrand={reveal.brandAt} startClock={reveal.clockAt} speed={reveal.speed}
            onCouncil={() => nav("/council")} />

          <div className="byline">{byline}</div>
          <StatBars stats={stats} />
          <CostIndicator data={costData} />
          <FactoryDock pending={factoryPending} onRefresh={refreshFactory} />
          <ConfirmationDock />
          <HandoffDock />
          <SoundGate />

          {/* center title types in LAST, after roster + params */}
          <OrbTitleStack projectLabel={projectLabel} agentName={agentName}
            centerAt={reveal.centerAt} speed={reveal.speed} />

          <main className="splash-main">
            {/* LEFT: agent roster — types in FIRST, top-down */}
            <AgentRosterPanel statusData={statusData} headline={headline} responses={responses}
              headlineAt={reveal.headlineAt} agentsAt={reveal.agentsAt} speed={reveal.speed}
              rowRef={registerRow} onAgentClick={onAgentClick}
              onDismissResponse={dismissResponse} onNavigate={onNavigate} />
            {/* RIGHT: system parameters — types in SECOND, top-down */}
            <SystemParamsPanel statusData={statusData}
              paramsAt={reveal.paramsAt} speed={reveal.speed} />
          </main>

          <CommandConsole connected={connected} onResult={setResult}
              voiceText={voiceText} voiceState={convState} onVoiceExecuted={handleVoiceExecuted} />

          <ActivityFeed activity={activity} />

          {/* response branches out (with a connector line) from its agent; draggable */}
          {result && (
            <ResultBranch result={result} anchorEl={agentRowsRef.current[result.agent]}
              onClose={() => setResult(null)} />
          )}
        </>
      )}
    </div>
  );
}

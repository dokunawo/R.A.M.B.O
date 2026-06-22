// SplashScreen.js
import React, { useState, useEffect, useRef, useCallback } from "react";
import { Canvas } from "@react-three/fiber";
import { EffectComposer, Bloom, ChromaticAberration } from "@react-three/postprocessing";
import { Vector2 } from "three";
import RamboOrb3D from "./RamboOrb3D";
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
  idle:    "#4a5568",
  offline: "#2a3040",
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

function useAgentStatus() {
  const [data, setData] = useState(null);
  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await fetch("http://localhost:8000/agents/status");
        if (!res.ok) throw new Error();
        if (!cancelled) setData(await res.json());
      } catch {}
    };
    poll();
    const id = setInterval(poll, 2000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);
  return data;
}

// Typewriter that waits `startMs` before typing `text` one char at a time.
// Re-runs on mount, so the whole cascade restarts when the console appears.
function useDelayedTypewriter(text, speed, startMs) {
  const [out, setOut] = useState("");
  useEffect(() => {
    setOut("");
    let i = 0;
    let intId;
    const startTimer = setTimeout(() => {
      intId = setInterval(() => {
        i += 1;
        setOut(text.slice(0, i));
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
    const t = setTimeout(() => setOn(true), Math.max(0, startMs));
    return () => clearTimeout(t);
  }, [startMs]);
  return on;
}

// Build a top-down reveal timeline: headline → agents → params → center title.
// Each item's start time is the cumulative length of everything before it, so
// items reveal one after another in reading order.
const REVEAL_SPEED = 15; // ms per character
const REVEAL_GAP   = 70; // ms pause between items
function buildReveal(headline, agentNames, paramKeys, centerLines) {
  let t = 0;
  const at = (s) => { const start = t; t += s.length * REVEAL_SPEED + REVEAL_GAP; return start; };
  return {
    speed:      REVEAL_SPEED,
    headlineAt: at(headline),
    agentsAt:   agentNames.map(at),
    paramsAt:   paramKeys.map(at),
    centerAt:   centerLines.map(at),
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

/* ------------------------------------------------------------------ */
/*  PHASE 1 — TRANSMISSION SCREEN                                       */
/* ------------------------------------------------------------------ */

function TransmissionScreen({ onAdvance }) {
  const [progress, setProgress] = useState(0);
  const [logLines, setLogLines] = useState([]);
  const [booting,  setBooting]  = useState(false);
  const onAdvanceRef = useRef(onAdvance);
  onAdvanceRef.current = onAdvance;       // always call the latest callback

  const SCAN_DURATION = 4200; // bar fills first, then the log finishes

  // Scan bar fills once (empty deps → not restarted by parent re-renders)
  useEffect(() => {
    const start = Date.now();
    const id = setInterval(() => {
      const pct = Math.min(100, ((Date.now() - start) / SCAN_DURATION) * 100);
      setProgress(pct);
      if (pct >= 100) clearInterval(id);
    }, 30);
    return () => clearInterval(id);
  }, []);

  // Boot log types in under the bar; after the last line ("ALL SYSTEMS
  // NOMINAL") show "NOW BOOTING UP", then transition.
  useEffect(() => {
    const START_DELAY   = 700;
    const LINE_INTERVAL = 480;
    const timers = BOOT_LOG.map((line, i) =>
      setTimeout(() => setLogLines(prev => [...prev, line]), START_DELAY + i * LINE_INTERVAL)
    );
    const bootAt = START_DELAY + BOOT_LOG.length * LINE_INTERVAL + 250;
    timers.push(setTimeout(() => setBooting(true), bootAt));
    timers.push(setTimeout(() => onAdvanceRef.current(), bootAt + 1100));
    return () => timers.forEach(clearTimeout);
  }, []);

  // scan label rotates through the steps as one continuous bar fills
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

      {/* All loading text housed inside / over the orb, centered */}
      <div className="tx-content tx-content-overlay">
        <div className="tx-emblem-title">R.A.M.B.O</div>
        <div className="tx-emblem-operator">RESPONSIVE AUTONOMOUS MULTI-BRAIN OPERATOR</div>

        <p className="tx-label">[ R.A.M.B.O SYSTEM ]</p>
        <p className="tx-subtitle">STANDBY FOR NEURAL SYNC</p>

        <div className="tx-status">
          <span className="tx-status-dot" />
          <span className="tx-status-text">BOOTING UP</span>
        </div>

        <div className="tx-scan-block">
          <p className="tx-scan-step">{scanLabel}</p>
          <div className="tx-progress-track">
            <div className="tx-progress-fill" style={{ width: `${progress}%` }} />
          </div>
          <p className="tx-progress-label">{Math.floor(progress)}%</p>
        </div>

        {/* boot log */}
        <div className="tx-boot-log">
          {logLines.map((line, i) => (
            <div key={i} className="tx-boot-line">{line}</div>
          ))}
          {booting
            ? <div className="tx-boot-line tx-now-booting">&gt; NOW BOOTING UP</div>
            : <span className="tx-boot-cursor">█</span>}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  PHASE 2 — LEFT: AGENT ROSTER (names, roles, descriptions, status) */
/* ------------------------------------------------------------------ */

function RosterRow({ agent, status, startMs, speed }) {
  const revealed  = useRevealAt(startMs);
  const typedName = useDelayedTypewriter(agent.name, speed, startMs);
  return (
    <li className={`brief-agent-entry${revealed ? " revealed" : ""}`}>
      <div className="brief-agent-header">
        <AgentDot status={status} />
        <span className="brief-agent-name neon-agent">{typedName}</span>
        <span className="brief-agent-role">{agent.role}</span>
        <span className="brief-agent-badge neon-badge" style={{ color: STATUS_COLORS[status] }}>
          {STATUS_LABELS[status]}
        </span>
      </div>
      <p className="brief-agent-desc">{agent.desc}</p>
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
  return (
    <div className={`brief-param-row${revealed ? " revealed" : ""}`}>
      <span className="brief-param-key">{typedKey}</span>
      <span className="brief-param-val">{value}</span>
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
      <div className="project-label">{p}</div>
      <div className="title-banner">{t}</div>
      <div className="subtitle">{s}</div>
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
/*  ICON PACK                                                           */
/* ------------------------------------------------------------------ */

const Icon = {
  Power:    () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M12 2v9" strokeLinecap="round" /><path d="M18.4 6.6a9 9 0 1 1-12.8 0" strokeLinecap="round" /></svg>,
  Mic:      () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="9" y="2" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" strokeLinecap="round" /></svg>,
  VideoOff: () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M2 2l20 20" /><path d="M15 8h2a2 2 0 0 1 2 2v1l3-2v8l-3-2v1a2 2 0 0 1-.4 1.2" strokeLinecap="round" strokeLinejoin="round" /><path d="M3 6.4A2 2 0 0 0 2 8v8a2 2 0 0 0 2 2h9a2 2 0 0 0 1.4-.6" strokeLinecap="round" strokeLinejoin="round" /></svg>,
  Settings: () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1" strokeLinecap="round" /></svg>,
  Hand:     () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M8 11V5a1.5 1.5 0 0 1 3 0v5" strokeLinecap="round" /><path d="M11 10V4a1.5 1.5 0 0 1 3 0v6" strokeLinecap="round" /><path d="M14 10V6a1.5 1.5 0 0 1 3 0v7" strokeLinecap="round" /><path d="M8 11l-1.5-1.3a1.4 1.4 0 0 0-2 2L8 16a6 6 0 0 0 6 2h1a5 5 0 0 0 5-5v-2" strokeLinecap="round" strokeLinejoin="round" /></svg>,
  Chat:     () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M21 11.5a8.4 8.4 0 0 1-8.9 8.4 9 9 0 0 1-3.4-.7L3 20l1-4.5A8.4 8.4 0 1 1 21 11.5Z" strokeLinejoin="round" /></svg>,
  Terminal: () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M4 17l5-5-5-5" strokeLinecap="round" strokeLinejoin="round" /><path d="M12 19h8" strokeLinecap="round" /></svg>,
  Wifi:     () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M2 8.5a16 16 0 0 1 20 0" strokeLinecap="round" /><path d="M5 12a11 11 0 0 1 14 0" strokeLinecap="round" /><path d="M8.5 15.5a6 6 0 0 1 7 0" strokeLinecap="round" /><circle cx="12" cy="19" r="1" fill="currentColor" /></svg>,
  Map:      () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M9 3 3 5v16l6-2 6 2 6-2V3l-6 2-6-2Z" strokeLinejoin="round" /><path d="M9 3v16M15 5v16" /></svg>,
  Collapse: () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M15 9 21 3" strokeLinecap="round" strokeLinejoin="round" /><path d="M9 15 3 21" strokeLinecap="round" strokeLinejoin="round" /><path d="M21 9V3h-6" strokeLinecap="round" strokeLinejoin="round" /><path d="M3 15v6h6" strokeLinecap="round" strokeLinejoin="round" /></svg>,
};

const DOCK_ICONS = [
  Icon.Power, Icon.Mic, Icon.VideoOff, Icon.Settings, Icon.Hand,
  Icon.Chat,  Icon.Terminal, Icon.Wifi, Icon.Map, Icon.Collapse,
];

/* ------------------------------------------------------------------ */
/*  ROOT — phase management                                             */
/* ------------------------------------------------------------------ */

export default function SplashScreen({
  projectLabel = "PROJECT: RAMBO",
  agentName    = "R.A.M.B.O",
  title        = "MK III",
  byline       = "BY DANIEL",
  headline     = "System Online",
  stats = [
    { label: "CPU",  value: 28.2,  displayValue: "28.2%" },
    { label: "RAM",  value: 20.5,  max: 64,   displayValue: "20.5G" },
    { label: "GPU",  value: 14,    displayValue: "14%" },
    { label: "VRAM", value: 4.1,   max: 24,   displayValue: "4.1G" },
    { label: "DSK",  value: 731.2, max: 1000, displayValue: "731.2G" },
  ],
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

  const statusData = useAgentStatus();

  const clockFmt = () =>
    new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const [clockStr, setClockStr] = useState(clockFmt);
  useEffect(() => {
    const id = setInterval(() => setClockStr(clockFmt()), 1000); // tick seconds
    return () => clearInterval(id);
  }, []);

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
  // roster headline → agents top-down → params top-down → center title.
  const reveal = buildReveal(
    headline,
    AGENT_ROSTER.map(a => a.name),
    PARAM_KEYS,
    [projectLabel, agentName, CENTER_SUBTITLE],
  );

  return (
    <div className={`splash-root${fading ? " phase-fading" : ""}`}>

      {phase === "transmission" && (
        <TransmissionScreen onAdvance={goMain} />
      )}

      {phase === "main" && (
        <>
          {/* full-screen orb */}
          <div className="orb-canvas">
            <Canvas camera={{ position: [0, 0, 4.2], fov: 45 }} gl={{ antialias: true, alpha: true }}>
              <RamboOrb3D mouseRef={mouseRef} />
              <EffectComposer>
                <Bloom luminanceThreshold={0.15} luminanceSmoothing={0.9}
                  intensity={1.4} mipmapBlur radius={0.8} />
                <ChromaticAberration offset={new Vector2(0.0012, 0.0012)}
                  radialModulation={false} modulationOffset={0} />
              </EffectComposer>
            </Canvas>
          </div>

          <div className="splash-grid-overlay" />

          <header className="splash-topbar glitch-in">
            <div className="topbar-left">
              <span className="brand-mark neon-brand">{agentName} {title.replace(" ", ".")}</span>
              <span className="topbar-divider" />
              <span className="topbar-tab">SYSTEM</span>
              <span className="topbar-tab">LOGS</span>
            </div>
            <div className="topbar-right">
              <span className="topbar-time neon-clock">{clockStr}</span>
            </div>
          </header>

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
              {stats.map(s => <StatBar key={s.label} {...s} />)}
            </div>
            <nav className="dock">
              {DOCK_ICONS.map((IconCmp, i) => (
                <button className="dock-btn" key={i} type="button"><IconCmp /></button>
              ))}
            </nav>
          </footer>
        </>
      )}
    </div>
  );
}

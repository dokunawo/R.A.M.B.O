// SplashScreen.js
import React, { useState, useEffect, useRef, useCallback } from "react";
import { Canvas } from "@react-three/fiber";
import { EffectComposer, Bloom } from "@react-three/postprocessing";
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

function RamboEmblem() {
  return (
    <div className="tx-emblem-wrap">
      {/* The exact same orb as Phase 2 (particles + plasma core + bloom),
          just contained here — no network webs. */}
      <div className="tx-plasma-big">
        <Canvas camera={{ position: [0, 0, 4.2], fov: 45 }} gl={{ antialias: true, alpha: true }}>
          <RamboOrb3D />
          <EffectComposer>
            <Bloom luminanceThreshold={0.15} luminanceSmoothing={0.9}
              intensity={1.4} mipmapBlur radius={0.8} />
          </EffectComposer>
        </Canvas>
      </div>
      <div className="tx-emblem-title">R.A.M.B.O</div>
      <div className="tx-emblem-operator">RESPONSIVE AUTONOMOUS MULTI-BRAIN OPERATOR</div>
    </div>
  );
}

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
      <div className="hud-dot-grid" />

      <div className="tx-content">
        <RamboEmblem />

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

        {/* boot log — moved here from old Phase 2 center */}
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

function AgentRosterPanel({ statusData, headline }) {
  const agents   = statusData?.agents ?? AGENT_ROSTER.map(a => ({ name: a.name, status: "offline" }));
  const agentMap = Object.fromEntries(agents.map(a => [a.name.toLowerCase(), a.status]));

  return (
    <aside className="roster-panel glitch-in">
      <h1 className="headline system-online">{headline}</h1>
      <div className="brief-section-label neon-label">AGENT ROSTER</div>
      <ul className="brief-agent-list">
        {AGENT_ROSTER.map(a => {
          const status = agentMap[a.key] ?? "offline";
          return (
            <li key={a.key} className="brief-agent-entry">
              <div className="brief-agent-header">
                <AgentDot status={status} />
                <span className="brief-agent-name neon-agent">{a.name}</span>
                <span className="brief-agent-role">{a.role}</span>
                <span className="brief-agent-badge neon-badge" style={{ color: STATUS_COLORS[status] }}>
                  {STATUS_LABELS[status]}
                </span>
              </div>
              <p className="brief-agent-desc">{a.desc}</p>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}

/* ------------------------------------------------------------------ */
/*  PHASE 2 — RIGHT: SYSTEM PARAMETERS                                 */
/* ------------------------------------------------------------------ */

function SystemParamsPanel({ statusData }) {
  const overseer = statusData?.overseer ?? { status: "offline" };

  return (
    <aside className="agent-panel glitch-in">
      <div className="agent-section-label neon-label">SYSTEM PARAMETERS</div>
      <div className="brief-params">
        {[
          ["DESIGNATION", "R.A.M.B.O"],
          ["VERSION",     "VERSION III"],
          ["CLEARANCE",   "AUTHORIZED"],
          ["BACKEND",     "localhost:8000"],
          ["PROTOCOL",    "HTTP / WebSocket"],
          ["AGENTS",      `${AGENT_ROSTER.length} REGISTERED`],
          ["OVERSEER",    STATUS_LABELS[overseer.status] ?? "OFFLINE"],
          ["TIMEZONE",    "America/Detroit"],
          ["BUILD",       "DEVELOPMENT"],
          ["OPERATOR",    "DANIEL"],
        ].map(([k, v]) => (
          <div key={k} className="brief-param-row">
            <span className="brief-param-key">{k}</span>
            <span className="brief-param-val">{v}</span>
          </div>
        ))}
      </div>
    </aside>
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

  const [clockStr, setClockStr] = useState(
    () => new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
  );
  useEffect(() => {
    const id = setInterval(() =>
      setClockStr(new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })), 10000);
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
              <span className="topbar-time">{clockStr}</span>
            </div>
          </header>

          <div className="byline">{byline}</div>

          <div className="orb-title-stack glitch-in">
            <div className="project-label">{projectLabel}</div>
            <div className="title-banner">{agentName}</div>
            <div className="subtitle">Responsive Autonomous Multi-Brain Operator</div>
          </div>

          <main className="splash-main">
            {/* LEFT: agent roster with descriptions + live status */}
            <AgentRosterPanel statusData={statusData} headline={headline} />
            {/* RIGHT: system parameters (replaces old status panel) */}
            <SystemParamsPanel statusData={statusData} />
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

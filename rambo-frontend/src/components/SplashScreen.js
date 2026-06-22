// SplashScreen.js
import React, { useState, useEffect, useRef, useMemo } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { EffectComposer, Bloom } from "@react-three/postprocessing";
import RamboOrb3D from "./RamboOrb3D";
import { ramboPlasmaVertexShader, ramboPlasmaFragmentShader } from "./RamboOrbShaders";
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
const STEP_DURATION_MS = 2100; // ms per scan step (~6.3s total for 3 steps)

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

function useLiveClock() {
  const [t, setT] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setT(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return t;
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
/*  MINI PLASMA — reusable living plasma canvas (no ring)              */
/* ------------------------------------------------------------------ */

function MiniPlasmaScene({ size = 1.15 }) {
  const ref = useRef();
  const mat = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: ramboPlasmaVertexShader,
        fragmentShader: ramboPlasmaFragmentShader,
        uniforms: {
          uTime:   { value: 0 },
          uBreath: { value: 0 },
          uColor:  { value: new THREE.Color("#fff4da") },
        },
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        side: THREE.DoubleSide,
      }),
    []
  );

  useFrame(({ clock, camera }) => {
    const t = clock.getElapsedTime();
    mat.uniforms.uTime.value   = t;
    mat.uniforms.uBreath.value = (Math.sin(t * 1.8) + 1.0) * 0.5;
    if (ref.current) ref.current.quaternion.copy(camera.quaternion);
  });

  return (
    <mesh ref={ref} material={mat}>
      <planeGeometry args={[size * 2, size * 2]} />
    </mesh>
  );
}

function MiniPlasma({ pxSize = 130, sceneSize = 1.15, className = "" }) {
  return (
    <div
      className={`mini-plasma ${className}`}
      style={{ width: pxSize, height: pxSize, flexShrink: 0 }}
    >
      <Canvas
        camera={{ position: [0, 0, 3], fov: 45 }}
        gl={{ antialias: true, alpha: true }}
      >
        <MiniPlasmaScene size={sceneSize} />
      </Canvas>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  PHASE 1 — TRANSMISSION SCREEN                                       */
/* ------------------------------------------------------------------ */

function RamboEmblem() {
  const ticks = Array.from({ length: 48 }, (_, i) => {
    const angle = (i / 48) * Math.PI * 2 - Math.PI / 2;
    const isMaj = i % 12 === 0;
    const isMid = i % 4 === 0;
    const inner = isMaj ? 78 : isMid ? 82 : 85;
    return {
      x1: Math.cos(angle) * inner, y1: Math.sin(angle) * inner,
      x2: Math.cos(angle) * 91,   y2: Math.sin(angle) * 91,
      w: isMaj ? 1.5 : 0.5,
      op: isMaj ? 0.8 : isMid ? 0.45 : 0.2,
    };
  });

  return (
    <div className="tx-emblem-wrap">
      <svg viewBox="-110 -125 220 265" className="tx-emblem-svg">
        {/* atmosphere ring */}
        <circle r="97" fill="none" stroke="#e8b15a" strokeWidth="0.4" strokeDasharray="2 6" opacity="0.2" />
        {/* tick marks */}
        {ticks.map((tk, i) => (
          <line key={i} x1={tk.x1} y1={tk.y1} x2={tk.x2} y2={tk.y2}
            stroke="#e8b15a" strokeWidth={tk.w} opacity={tk.op} />
        ))}
        {/* main ring */}
        <circle r="75" fill="none" stroke="#e8b15a" strokeWidth="1.5" opacity="0.95" />
        {/* inner ring */}
        <circle r="59" fill="rgba(232,177,90,0.03)" stroke="#e8b15a" strokeWidth="0.5" opacity="0.45" />
        {/* cardinal cross outside */}
        <line x1="-75" y1="0" x2="-97" y2="0"  stroke="#e8b15a" strokeWidth="1" opacity="0.65" />
        <line x1="75"  y1="0" x2="97"  y2="0"  stroke="#e8b15a" strokeWidth="1" opacity="0.65" />
        <line x1="0" y1="-75" x2="0"  y2="-97" stroke="#e8b15a" strokeWidth="1" opacity="0.65" />
        <line x1="0" y1="75"  x2="0"  y2="97"  stroke="#e8b15a" strokeWidth="1" opacity="0.65" />
        {/* inner reticle */}
        <line x1="-28" y1="0" x2="28" y2="0" stroke="#e8b15a" strokeWidth="0.4" opacity="0.3" />
        <line x1="0" y1="-28" x2="0" y2="28" stroke="#e8b15a" strokeWidth="0.4" opacity="0.3" />
        {/* inner corner brackets */}
        {[[-1,-1],[1,-1],[1,1],[-1,1]].map(([sx, sy], i) => (
          <g key={i}>
            <line x1={sx*50} y1={sy*30} x2={sx*50} y2={sy*50} stroke="#e8b15a" strokeWidth="1" opacity="0.55" />
            <line x1={sx*30} y1={sy*50} x2={sx*50} y2={sy*50} stroke="#e8b15a" strokeWidth="1" opacity="0.55" />
          </g>
        ))}
        {/* labels below circle — plasma replaces center diamond */}
        <text textAnchor="middle" y="100" fill="#ffd98a" fontSize="12" letterSpacing="5"
          fontFamily="'JetBrains Mono', monospace" fontWeight="700">R.A.M.B.O</text>
        <text textAnchor="middle" y="115" fill="#e8b15a" fontSize="4.2" letterSpacing="1.5"
          fontFamily="'JetBrains Mono', monospace" opacity="0.75">RESPONSIVE AUTONOMOUS MULTI-BRAIN OPERATOR</text>
      </svg>
      {/* Living plasma at center — overlaid on the SVG */}
      <div className="tx-plasma-overlay">
        <Canvas camera={{ position: [0, 0, 3], fov: 45 }} gl={{ antialias: true, alpha: true }}>
          <MiniPlasmaScene size={1.12} />
        </Canvas>
      </div>
    </div>
  );
}

function TransmissionScreen({ onAdvance, statusData }) {
  const [scanStep, setScanStep] = useState(0);
  const [progress, setProgress]  = useState(0);
  const [visibleAgents, setVisibleAgents] = useState([]);

  // Agent batches revealed per completed scan step
  const agentBatches = [
    AGENT_ROSTER.slice(0, 3),
    AGENT_ROSTER.slice(3, 7),
    AGENT_ROSTER.slice(7, 10),
  ];

  useEffect(() => {
    let step  = 0;
    let start = Date.now();

    const tick = () => {
      const elapsed = Date.now() - start;
      const pct = Math.min(100, (elapsed / STEP_DURATION_MS) * 100);
      setProgress(pct);

      if (pct >= 100) {
        if (step < SCAN_STEPS.length - 1) {
          setVisibleAgents(prev => [...prev, ...agentBatches[step]]);
          step++;
          setScanStep(step);
          setProgress(0);
          start = Date.now();
        } else {
          // Final step complete — show remaining agents then advance
          setVisibleAgents([...AGENT_ROSTER]);
          clearInterval(id);
          setTimeout(onAdvance, 600);
        }
      }
    };

    const id = setInterval(tick, 30);
    return () => clearInterval(id);
  }, [onAdvance]); // eslint-disable-line react-hooks/exhaustive-deps

  const agents   = statusData?.agents ?? AGENT_ROSTER.map(a => ({ name: a.name, status: "offline" }));
  const agentMap = Object.fromEntries(agents.map(a => [a.name.toLowerCase(), a.status]));

  return (
    <div className="phase-screen tx-screen" onClick={onAdvance}>
      <div className="hud-dot-grid" />

      <div className="tx-content">
        <RamboEmblem />

        <p className="tx-label">[ R.A.M.B.O SYSTEM ]</p>
        <p className="tx-subtitle">STANDBY FOR NEURAL SYNC</p>

        <div className="tx-scan-block">
          <p className="tx-scan-step">{SCAN_STEPS[scanStep]}</p>
          <div className="tx-progress-track">
            <div className="tx-progress-fill" style={{ width: `${progress}%` }} />
          </div>
          <p className="tx-progress-label">{Math.floor(progress)}%</p>
        </div>

        {visibleAgents.length > 0 && (
          <div className="tx-agent-row">
            <div className="tx-roster-label neon-label">AGENT ROSTER</div>
            <div className="tx-agent-grid">
              {visibleAgents.map(a => {
                const status = agentMap[a.key] ?? "offline";
                return (
                  <div key={a.key} className="tx-agent-item">
                    <AgentDot status={status} />
                    <span className="tx-agent-name neon-agent">{a.name}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        <p className="tx-hint">CLICK ANYWHERE TO SKIP</p>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  PHASE 2 — MISSION BRIEFING                                          */
/* ------------------------------------------------------------------ */

function BriefingScreen({ onAdvance, statusData }) {
  const now = useLiveClock();
  const [logLines,        setLogLines]        = useState([]);
  const [progress,        setProgress]        = useState(0);
  const [progressStarted, setProgressStarted] = useState(false);

  // Stagger boot-log lines, then trigger progress bar once all lines are in
  useEffect(() => {
    const LINE_INTERVAL = 480;
    const timers = BOOT_LOG.map((line, i) =>
      setTimeout(() => setLogLines(prev => [...prev, line]), i * LINE_INTERVAL + 300)
    );
    const logEnd  = (BOOT_LOG.length - 1) * LINE_INTERVAL + 300 + 600;
    const progTmr = setTimeout(() => setProgressStarted(true), logEnd);
    return () => { timers.forEach(clearTimeout); clearTimeout(progTmr); };
  }, []);

  // Progress bar only runs after log finishes
  useEffect(() => {
    if (!progressStarted) return;
    const PROGRESS_DURATION = 2600;
    const start = Date.now();
    const id = setInterval(() => {
      const pct = Math.min(100, ((Date.now() - start) / PROGRESS_DURATION) * 100);
      setProgress(pct);
      if (pct >= 100) { clearInterval(id); setTimeout(onAdvance, 320); }
    }, 30);
    return () => clearInterval(id);
  }, [progressStarted, onAdvance]);

  const overseer = statusData?.overseer ?? { status: "offline" };
  const agents   = statusData?.agents   ?? AGENT_ROSTER.map(a => ({ name: a.name, status: "offline" }));
  const agentMap = Object.fromEntries(agents.map(a => [a.name.toLowerCase(), a.status]));

  const timeStr = now.toLocaleTimeString("en-US", {
    hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: "America/Detroit",
  });
  const dateStr = now.toLocaleDateString("en-US", {
    weekday: "short", year: "numeric", month: "short", day: "numeric", timeZone: "America/Detroit",
  });

  return (
    <div className="phase-screen brief-screen" onClick={onAdvance}>
      <div className="hud-dot-grid" />

      {/* LEFT — agent roster */}
      <aside className="brief-left">
        <div className="brief-section-label neon-label">AGENT ROSTER</div>
        <div className="brief-boot-label">Booting Up Agents</div>
        <ul className="brief-agent-list">
          {AGENT_ROSTER.map(a => {
            const status = agentMap[a.key] ?? "offline";
            return (
              <li key={a.key} className="brief-agent-entry">
                <div className="brief-agent-header">
                  <AgentDot status={status} />
                  <span className="brief-agent-name neon-agent">{a.name}</span>
                  <span className="brief-agent-role">{a.role}</span>
                  <span className="brief-agent-badge" style={{ color: STATUS_COLORS[status] }}>
                    {STATUS_LABELS[status]}
                  </span>
                </div>
                <p className="brief-agent-desc">{a.desc}</p>
              </li>
            );
          })}
        </ul>
      </aside>

      {/* CENTER — overseer + plasma + clock + boot log */}
      <div className="brief-center">
        <MiniPlasma pxSize={88} sceneSize={0.95} className="brief-plasma" />
        <div className="brief-overseer-label">OVERSEER</div>
        <div className="brief-overseer-name">R.A.M.B.O</div>
        <div className="brief-overseer-status">
          <AgentDot status={overseer.status} />
          <span style={{ color: STATUS_COLORS[overseer.status], fontSize: "8px", letterSpacing: "0.14em" }}>
            {STATUS_LABELS[overseer.status] ?? "OFFLINE"}
          </span>
        </div>
        <div className="brief-divider" />
        <div className="brief-clock">{timeStr}</div>
        <div className="brief-date">{dateStr}</div>
        <div className="brief-log">
          {logLines.map((line, i) => (
            <div key={i} className="brief-log-line">{line}</div>
          ))}
          <span className="brief-cursor">█</span>
        </div>
      </div>

      {/* RIGHT — system parameters */}
      <aside className="brief-right">
        <div className="brief-section-label">SYSTEM PARAMETERS</div>
        <div className="brief-params">
          {[
            ["DESIGNATION",  "R.A.M.B.O"],
            ["VERSION",      "VERSION III"],
            ["CLEARANCE",    "AUTHORIZED"],
            ["BACKEND",      "localhost:8000"],
            ["PROTOCOL",     "HTTP / WebSocket"],
            ["AGENTS",       `${AGENT_ROSTER.length} REGISTERED`],
            ["OVERSEER",     STATUS_LABELS[overseer.status] ?? "OFFLINE"],
            ["TIMEZONE",     "America/Detroit"],
            ["BUILD",        "DEVELOPMENT"],
            ["OPERATOR",     "DANIEL"],
          ].map(([k, v]) => (
            <div key={k} className="brief-param-row">
              <span className="brief-param-key">{k}</span>
              <span className="brief-param-val">{v}</span>
            </div>
          ))}
        </div>
      </aside>

      {/* bottom progress — only fills after log completes */}
      <div className="brief-footer">
        <div className="brief-progress-track">
          <div className="brief-progress-fill" style={{ width: `${progress}%` }} />
        </div>
        <p className="brief-progress-label">ESTABLISHING SECURE UPLINK... {Math.floor(progress)}%</p>
        <p className="brief-hint">CLICK ANYWHERE TO SKIP</p>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  PHASE 3 — NETWORK WEB OVERLAY                                       */
/* ------------------------------------------------------------------ */

// SVG overlay connecting UI zones with subtle dashed gold lines
function NetworkWeb() {
  return (
    <svg className="network-web" viewBox="0 0 100 100" preserveAspectRatio="none"
      xmlns="http://www.w3.org/2000/svg">
      <defs>
        <filter id="nwGlow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="0.4" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
      </defs>

      {/* topbar brand → title */}
      <line x1="5" y1="4" x2="39" y2="44"
        stroke="#e8b15a" strokeWidth="0.14" opacity="0.2" strokeDasharray="0.8 2" filter="url(#nwGlow)" />
      {/* title → agent panel top */}
      <line x1="61" y1="43" x2="79" y2="26"
        stroke="#e8b15a" strokeWidth="0.14" opacity="0.2" strokeDasharray="0.8 2" filter="url(#nwGlow)" />
      {/* orb edge → agent panel mid */}
      <line x1="63" y1="50" x2="79" y2="50"
        stroke="#e8b15a" strokeWidth="0.11" opacity="0.14" strokeDasharray="0.6 2.5" filter="url(#nwGlow)" />
      {/* agent panel bottom → dock */}
      <line x1="80" y1="74" x2="58" y2="93"
        stroke="#e8b15a" strokeWidth="0.14" opacity="0.2" strokeDasharray="0.8 2" filter="url(#nwGlow)" />
      {/* orb edge → stat panel */}
      <line x1="37" y1="57" x2="10" y2="86"
        stroke="#e8b15a" strokeWidth="0.14" opacity="0.2" strokeDasharray="0.8 2" filter="url(#nwGlow)" />
      {/* stat panel → dock */}
      <line x1="21" y1="87" x2="43" y2="93"
        stroke="#e8b15a" strokeWidth="0.11" opacity="0.14" strokeDasharray="0.6 2.5" filter="url(#nwGlow)" />

      {/* nodes at each endpoint */}
      {[
        [5, 4], [40, 44], [61, 43],
        [79, 26], [79, 50], [63, 50],
        [80, 74], [58, 93], [43, 93],
        [37, 57], [10, 86], [21, 87],
      ].map(([cx, cy], i) => (
        <circle key={i} cx={cx} cy={cy} r="0.55"
          fill="#e8b15a" opacity="0.45" filter="url(#nwGlow)" />
      ))}
    </svg>
  );
}

/* ------------------------------------------------------------------ */
/*  PHASE 3 — AGENT STATUS PANEL (right side)                          */
/* ------------------------------------------------------------------ */

function AgentStatusPanel({ statusData }) {
  const overseer = statusData?.overseer ?? { name: "R.A.M.B.O", status: "offline" };
  const agents   = statusData?.agents   ?? AGENT_ROSTER.map(a => ({ name: a.name, status: "offline" }));

  return (
    <aside className="agent-panel glitch-in">
      <div className="agent-overseer-block">
        <div className="agent-section-label">OVERSEER</div>
        <div className="agent-overseer-row">
          <AgentDot status={overseer.status} />
          <span className="agent-overseer-name">{overseer.name}</span>
          <span className="agent-status-badge neon-badge" style={{ color: STATUS_COLORS[overseer.status] ?? STATUS_COLORS.offline }}>
            {STATUS_LABELS[overseer.status] ?? "OFFLINE"}
          </span>
        </div>
      </div>
      <div className="agent-divider" />
      <div className="agent-section-label">AGENTS</div>
      <ul className="agent-list">
        {agents.map(a => (
          <li key={a.name} className="agent-row">
            <AgentDot status={a.status} />
            <span className="agent-name neon-agent">{a.name}</span>
            <span className="agent-status-badge neon-badge" style={{ color: STATUS_COLORS[a.status] ?? STATUS_COLORS.offline }}>
              {STATUS_LABELS[a.status] ?? "OFFLINE"}
            </span>
          </li>
        ))}
      </ul>
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
  body         = "Initializing neural lattice… establishing multi-brain sync…",
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

  const advance = (next) => {
    setFading(true);
    setTimeout(() => { setPhase(next); setFading(false); }, 480);
  };

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
        <TransmissionScreen onAdvance={() => advance("briefing")} statusData={statusData} />
      )}

      {phase === "briefing" && (
        <BriefingScreen onAdvance={() => advance("main")} statusData={statusData} />
      )}

      {phase === "main" && (
        <>
          {/* Network web SVG behind all content */}
          <NetworkWeb />

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
            <section className="splash-left glitch-in">
              <h1 className="headline system-online">{headline}</h1>
              <p className="body-copy init-text neon-body">{body}</p>
            </section>
            <AgentStatusPanel statusData={statusData} />
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

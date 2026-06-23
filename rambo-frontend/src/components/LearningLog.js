import React, { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Canvas } from "@react-three/fiber";
import { EffectComposer, Bloom } from "@react-three/postprocessing";
import CosmicOrb from "./CosmicOrb";
import CosmicBackground from "./CosmicBackground";
import { usePageVoice, VoiceControls } from "./VoiceControls";
import { useSystemStats, useActivityFeed, StatBars, ActivityFeed, CommandInput } from "./SharedHUD";
import "./LearningLog.css";
import "./AgentPage.css";

const API = "http://localhost:8000";

const AGENT_NAV = [
  { key: "architect", name: "Architect", avatar: "🧠", color: "#7b6ff0" },
  { key: "engineer",  name: "Engineer",  avatar: "⚙️", color: "#e8b15a" },
  { key: "seeker",    name: "Seeker",    avatar: "🔍", color: "#00d4aa" },
  { key: "analyst",   name: "Analyst",   avatar: "📊", color: "#4a9eff" },
  { key: "sentinel",  name: "Sentinel",  avatar: "🛡️", color: "#ff4466" },
  { key: "steward",   name: "Steward",   avatar: "💰", color: "#22c55e" },
  { key: "link",      name: "Link",      avatar: "🔗", color: "#e879f9" },
  { key: "keeper",    name: "Keeper",    avatar: "📚", color: "#f59e0b" },
  { key: "echo",      name: "Echo",      avatar: "📡", color: "#06b6d4" },
  { key: "pilot",     name: "Pilot",     avatar: "🎯", color: "#fb923c" },
];

function LiveClock() {
  const [time, setTime] = useState(new Date());
  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  const date = time.toLocaleDateString("en-US", { month: "2-digit", day: "2-digit", year: "numeric" });
  const clock = time.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  return <span className="ll-clock">{date} — {clock}</span>;
}

function OrbBranch({ side, panelTop }) {
  const [dim, setDim] = useState({ w: window.innerWidth, h: window.innerHeight });
  useEffect(() => {
    const onResize = () => setDim({ w: window.innerWidth, h: window.innerHeight });
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const cx = dim.w / 2;
  const cy = dim.h / 2;
  const orbR = 120;

  const panelX = side === "left" ? 340 : dim.w - 340;
  const panelY = panelTop || cy;

  const dx = panelX - cx;
  const dy = panelY - cy;
  const dist = Math.sqrt(dx * dx + dy * dy);
  const ratio = orbR / Math.max(dist, 1);
  const startX = cx + dx * ratio;
  const startY = cy + dy * ratio;

  const cp1x = startX + dx * 0.4;
  const cp1y = startY;
  const cp2x = panelX - dx * 0.3;
  const cp2y = panelY;

  const color = "#ff4466";

  return (
    <svg className="ll-branch-svg" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id={`ll-grad-${side}`} x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor={color} stopOpacity="0.8" />
          <stop offset="100%" stopColor={color} stopOpacity="0.25" />
        </linearGradient>
      </defs>
      <path
        d={`M ${startX} ${startY} C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${panelX} ${panelY}`}
        fill="none" stroke={`url(#ll-grad-${side})`} strokeWidth="1.4"
      />
      <circle cx={startX} cy={startY} r="3" fill={color} opacity="0.9">
        <animate attributeName="r" values="3;5;3" dur="2.5s" repeatCount="indefinite" />
        <animate attributeName="opacity" values="0.9;0.5;0.9" dur="2.5s" repeatCount="indefinite" />
      </circle>
      <circle cx={panelX} cy={panelY} r="3" fill={color} opacity="0.6" />
    </svg>
  );
}

function LearningLog() {
  const navigate = useNavigate();
  const { micActive, toggleMic, state: convState, levelRef: audioLevelRef } = usePageVoice();
  const sysStats = useSystemStats();
  const { activity, connected } = useActivityFeed();
  const [learnings, setLearnings] = useState([]);

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

  const fetchLearnings = useCallback(async () => {
    try {
      const r = await fetch(`${API}/learning/log`);
      if (r.ok) setLearnings(await r.json());
    } catch {}
  }, []);

  useEffect(() => {
    fetchLearnings();
    const id = setInterval(fetchLearnings, 5000);
    return () => clearInterval(id);
  }, [fetchLearnings]);

  return (
    <div className="ll-root">
      <div className="ll-orb-bg">
        <Canvas camera={{ position: [0, 0, 4.2], fov: 45 }}
          dpr={[1, 1.5]} gl={{ antialias: true, alpha: true, premultipliedAlpha: false, powerPreference: 'high-performance', stencil: false }}>
          <CosmicBackground />
          <CosmicOrb mouseRef={mouseRef} audioLevelRef={audioLevelRef} />
          <EffectComposer>
            <Bloom luminanceThreshold={0.7} luminanceSmoothing={0.95}
              intensity={0.6} radius={0.5} />
          </EffectComposer>
        </Canvas>
      </div>

      <div className="ll-grid-overlay" />

      <OrbBranch side="left" />
      <OrbBranch side="right" />

      <header className="ll-topbar">
        <button className="ll-back-btn" onClick={() => navigate("/console")}>
          ← COMMAND CENTER
        </button>
        <div className="ll-topbar-title">LEARNING LOG</div>
        <div className="ll-topbar-right">
          <span className="ll-council-link" onClick={() => navigate("/council")}>
            ◆ COUNCIL VIEW
          </span>
          <LiveClock />
        </div>
      </header>

      {/* LEFT PANEL — identity + operational info */}
      <div className="ll-left-panel">
        <div className="ll-panel-frame">
          <div className="ll-section-label" style={{ borderColor: "#ff4466" }}>◆ SYSTEM IDENTITY</div>
          <div className="ll-profile-row">
            <span className="ll-avatar">🧬</span>
            <div>
              <div className="ll-agent-name">Learning Log</div>
              <div className="ll-agent-role">Pattern Recognition</div>
            </div>
          </div>
          <div className="ll-agent-desc">
            A running record of patterns, corrections, and adaptations across
            all operational cycles.
          </div>
        </div>

        <div className="ll-panel-frame">
          <div className="ll-section-label" style={{ borderColor: "#ff4466" }}>◆ OPERATIONAL LEARNING</div>
          <div className="ll-op-text">
            R.A.M.B.O continuously adapts through operator corrections,
            task outcomes, and pattern recognition across all agent interactions.
          </div>
          <div className="ll-stat-row">
            <span className="ll-stat-key">ENTRIES</span>
            <span className="ll-stat-val">{learnings.length}</span>
          </div>
          <div className="ll-stat-row">
            <span className="ll-stat-key">STATUS</span>
            <span className="ll-stat-val" style={{ color: "#00ff88" }}>ACTIVE</span>
          </div>
        </div>
      </div>

      {/* RIGHT PANEL — recent learnings list */}
      <div className="ll-right-panel">
        <div className="ll-panel-frame">
          <div className="ll-section-label" style={{ borderColor: "#06b6d4" }}>◆ RECENT LEARNINGS</div>
          {learnings.length === 0 ? (
            <div className="ll-empty">
              No learnings recorded yet. Learnings are captured automatically
              as R.A.M.B.O processes tasks and receives operator feedback.
            </div>
          ) : (
            <div className="ll-learn-list">
              {learnings.slice(0, 8).map((l, i) => (
                <div key={i} className="ll-learn-item">
                  <div className="ll-learn-head">
                    <span className="ll-learn-source">{l.source || "System"}</span>
                    <span className="ll-learn-time">{l.time || "—"}</span>
                  </div>
                  <div className="ll-learn-text">{l.text}</div>
                  {l.category && <span className="ll-learn-cat">{l.category}</span>}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <StatBars stats={sysStats} />
      <CommandInput connected={connected} />
      <ActivityFeed activity={activity} />

      <nav className="ap-quick-switch">
        {AGENT_NAV.map(a => (
          <button key={a.key} className="ap-qs-btn"
            style={{ "--agent-color": a.color, borderColor: "rgba(255,255,255,0.1)" }}
            onClick={() => navigate(`/agent/${a.key}`)} title={a.name}>
            <span className="ap-qs-avatar">{a.avatar}</span>
            <span className="ap-qs-name">{a.name}</span>
          </button>
        ))}
        <span className="ap-qs-divider" />
        <button className="ap-qs-btn ap-qs-nav" style={{ "--agent-color": "#e8b15a", borderColor: "rgba(255,255,255,0.1)" }}
          onClick={() => navigate("/council")} title="Round Table">
          <span className="ap-qs-avatar">⚔️</span>
          <span className="ap-qs-name">Council</span>
        </button>
        <button className="ap-qs-btn ap-qs-nav ap-qs-active" style={{ "--agent-color": "#e8b15a", borderColor: "#e8b15a" }}
          title="Learning Log">
          <span className="ap-qs-avatar">📜</span>
          <span className="ap-qs-name">Log</span>
        </button>
      </nav>

      <VoiceControls micActive={micActive} toggleMic={toggleMic} convState={convState} />
    </div>
  );
}

export default LearningLog;

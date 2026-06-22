import React, { useState, useEffect, useRef, useCallback, Component } from "react";
import { useNavigate } from "react-router-dom";
import { Canvas, useFrame } from "@react-three/fiber";
import { EffectComposer, Bloom, ChromaticAberration } from "@react-three/postprocessing";
import { Vector2 } from "three";
import CosmicOrb from "./CosmicOrb";
import "./RoundTable.css";

const API = "http://localhost:8000";

class OrbErrorBoundary extends Component {
  constructor(props) { super(props); this.state = { hasError: false }; }
  static getDerivedStateFromError() { return { hasError: true }; }
  render() { return this.state.hasError ? null : this.props.children; }
}

const AGENTS = [
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

const STATUS_COLORS = {
  online: "#00ff88", working: "#e8b15a", idle: "#8fa0b5", offline: "#5a6575",
};

function OrbitRing() {
  const ref = useRef();
  useFrame((_, delta) => { if (ref.current) ref.current.rotation.z += delta * 0.03; });
  const segments = 128;
  const radius = 3.2;
  const pts = [];
  for (let i = 0; i <= segments; i++) {
    const a = (i / segments) * Math.PI * 2;
    pts.push(Math.cos(a) * radius, Math.sin(a) * radius, 0);
  }
  return (
    <line ref={ref}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[new Float32Array(pts), 3]} />
      </bufferGeometry>
      <lineBasicMaterial color="#e8b15a" transparent opacity={0.12} />
    </line>
  );
}

function RoundTable() {
  const navigate = useNavigate();
  const [statusMap, setStatusMap] = useState({});

  const fetchStatus = useCallback(async () => {
    try {
      const r = await fetch(`${API}/agents/status`);
      if (r.ok) {
        const data = await r.json();
        const map = {};
        (data.agents || []).forEach(a => { map[a.name.toLowerCase()] = a.status; });
        setStatusMap(map);
      }
    } catch {}
  }, []);

  useEffect(() => {
    fetchStatus();
    const id = setInterval(fetchStatus, 2000);
    return () => clearInterval(id);
  }, [fetchStatus]);

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

  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setElapsed(t => t + 0.02), 33);
    return () => clearInterval(id);
  }, []);

  const orbitRadius = Math.min(window.innerWidth, window.innerHeight) * 0.32;
  const cx = window.innerWidth / 2;
  const cy = window.innerHeight / 2 + 20;

  return (
    <div className="rt-root">
      {/* full-screen orb */}
      <div className="rt-orb-bg">
        <OrbErrorBoundary>
          <Canvas camera={{ position: [0, 0, 4.2], fov: 45 }}
            dpr={[1, 1.5]} gl={{ antialias: true, alpha: true }}>
            <CosmicOrb mouseRef={mouseRef} />
            <OrbitRing />
            <EffectComposer>
              <Bloom luminanceThreshold={0.15} luminanceSmoothing={0.9}
                intensity={1.4} radius={0.8} />
              <ChromaticAberration offset={new Vector2(0.0012, 0.0012)}
                radialModulation={false} modulationOffset={0} />
            </EffectComposer>
          </Canvas>
        </OrbErrorBoundary>
      </div>

      <div className="rt-grid-overlay" />

      <header className="rt-topbar">
        <button className="rt-back-btn" onClick={() => navigate("/console")}>
          ← COMMAND CENTER
        </button>
        <div className="rt-topbar-title">ROUND TABLE</div>
        <div className="rt-topbar-right">
          <span className="rt-clock">
            {new Date().toLocaleDateString("en-US", {
              month: "2-digit", day: "2-digit", year: "numeric",
            })}
          </span>
        </div>
      </header>

      <div className="rt-subtitle">
        The council table. Click any agent to enter their domain — or watch
        them orbit the core, each linked to an active role.
      </div>

      {/* orbiting agent nodes */}
      <div className="rt-agents-layer">
        {AGENTS.map((agent, i) => {
          const angle = (i / AGENTS.length) * Math.PI * 2 + elapsed * 0.15;
          const x = cx + Math.cos(angle) * orbitRadius - 32;
          const y = cy + Math.sin(angle) * orbitRadius - 32;
          const s = statusMap[agent.key] || "idle";
          return (
            <div key={agent.key} className="rt-agent-node"
              style={{ left: x, top: y, borderColor: agent.color }}
              onClick={() => navigate(`/agent/${agent.key}`)}>
              <div className="rt-agent-dot" style={{ background: STATUS_COLORS[s] }} />
              <span className="rt-agent-avatar">{agent.avatar}</span>
              <span className="rt-agent-label" style={{ color: agent.color }}>{agent.name}</span>
            </div>
          );
        })}

        {/* connection lines from center to each agent */}
        <svg className="rt-lines" viewBox={`0 0 ${window.innerWidth} ${window.innerHeight}`}>
          {AGENTS.map((agent, i) => {
            const angle = (i / AGENTS.length) * Math.PI * 2 + elapsed * 0.15;
            const x = cx + Math.cos(angle) * orbitRadius;
            const y = cy + Math.sin(angle) * orbitRadius;
            return (
              <line key={agent.key} x1={cx} y1={cy} x2={x} y2={y}
                stroke={agent.color} strokeWidth="0.6" opacity="0.2" />
            );
          })}
        </svg>
      </div>

      <footer className="rt-footer">
        <span>R.A.M.B.O — Accuracy · Precision · Execution</span>
      </footer>
    </div>
  );
}

export default RoundTable;

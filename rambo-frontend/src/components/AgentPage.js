import React, { useState, useEffect, useCallback, useRef, Component } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Canvas } from "@react-three/fiber";
import { EffectComposer, Bloom, ChromaticAberration } from "@react-three/postprocessing";
import { Vector2 } from "three";
import CosmicOrb from "./CosmicOrb";
import CosmicBackground from "./CosmicBackground";
import { usePageVoice, VoiceControls, CommandLog } from "./VoiceControls";
import "./AgentPage.css";

class OrbErrorBoundary extends Component {
  constructor(props) { super(props); this.state = { hasError: false }; }
  static getDerivedStateFromError() { return { hasError: true }; }
  componentDidCatch(err) { console.error("[OrbErrorBoundary]", err); }
  render() { return this.state.hasError ? null : this.props.children; }
}

const API = "http://localhost:8000";

function LiveClock() {
  const [time, setTime] = useState(new Date());
  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  const date = time.toLocaleDateString("en-US", { month: "2-digit", day: "2-digit", year: "numeric" });
  const clock = time.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  return <span className="ap-clock">{date} — {clock}</span>;
}

const AGENT_META = {
  architect: {
    name: "Architect", role: "Strategic Planning",
    desc: "Plans the build before anyone writes a line of code. Decomposes goals into executable task hierarchies.",
    color: "#7b6ff0", avatar: "🧠",
    objectives: [
      "Break down goals into coherent, prioritized plans",
      "Maintain structural integrity across multi-step operations",
      "Guide task delegation to appropriate specialist agents",
      "Validate architecture decisions against system constraints",
    ],
  },
  engineer: {
    name: "Engineer", role: "Code Execution",
    desc: "Writes and ships the actual code. Generates and executes technical implementations with precision.",
    color: "#e8b15a", avatar: "⚙️",
    objectives: [
      "Implement code artifacts from Architect task specifications",
      "Ensure test coverage for all generated implementations",
      "Apply secure coding patterns by default",
      "Manage version-safe module integrations",
    ],
  },
  seeker: {
    name: "Seeker", role: "Intelligence Gathering",
    desc: "Goes and finds the answer. Gathering external intelligence — collecting, parsing, and returning live insights.",
    color: "#00d4aa", avatar: "🔍",
    objectives: [
      "Perform real-time web/API research on command",
      "Aggregate and cross-reference multiple data sources",
      "Surface key findings in structured, consumable format",
      "Score source reliability and freshness automatically",
    ],
  },
  analyst: {
    name: "Analyst", role: "Data Analysis",
    desc: "Turns raw numbers into a read. Spot-checks and extracts the pattern in messy data.",
    color: "#4a9eff", avatar: "📊",
    objectives: [
      "Classify data sets across time, identity, and structures",
      "Build predictive assessments for probabilistic outcomes",
      "Generate visual-ready data summaries for the operator",
      "Track confidence and anomaly levels across all data feeds",
    ],
  },
  sentinel: {
    name: "Sentinel", role: "Security & Compliance",
    desc: "The gatekeeper. Nothing risky moves without sign-off here. Controls the approval queue and the audit trail.",
    color: "#ff4466", avatar: "🛡️",
    objectives: [
      "Review all agent actions for security and compliance",
      "Maintain and enforce the approval queue",
      "Block unauthorized access to sensitive resources",
      "Track approval history and generate audit reports",
    ],
  },
  steward: {
    name: "Steward", role: "Resource & Budget Management",
    desc: "Income, expenses, savings, and investments — tracked, never missed, without approval.",
    color: "#22c55e", avatar: "💰",
    objectives: [
      "Track all financial transactions by category",
      "Maintain real-time budget with forecasting projections",
      "Alert on anomalous spending or missed savings targets",
      "Provide monthly summaries and variance analysis",
    ],
  },
  link: {
    name: "Link", role: "External Integration",
    desc: "Designs how R.A.M.B.O talks to the outside world. API calls, webhooks, and data connectors.",
    color: "#e879f9", avatar: "🔗",
    objectives: [
      "Integrate third-party services via REST/GraphQL/WebSocket",
      "Maintain connection health and failover mechanisms",
      "Transform external data formats to internal schema",
      "Enforce rate-limiting and connection security",
    ],
  },
  keeper: {
    name: "Keeper", role: "Storage & Memory",
    desc: "Owns the notebook — what gets remembered and how. Persists knowledge across operational cycles.",
    color: "#f59e0b", avatar: "📚",
    objectives: [
      "Store and retrieve context across all agent sessions",
      "Maintain structured knowledge base with relationships",
      "Garbage-collect stale or contradicted memories",
      "Serve fast lookups during active orchestrations",
    ],
  },
  echo: {
    name: "Echo", role: "Communication & Synthesis",
    desc: "The voice Sir actually hears. Synthesizes results from all agents into clear, actionable responses.",
    color: "#06b6d4", avatar: "📡",
    objectives: [
      "Compose final operator-facing responses from agent outputs",
      "Maintain conversational tone and formatting standards",
      "Deduplicate and prioritize multi-agent result sets",
      "Adapt detail level to operator context and preferences",
    ],
  },
  pilot: {
    name: "Pilot", role: "Task Management & Coordination",
    desc: "Keeps track of what's open, what's done, and what's next. Runs the execution queue.",
    color: "#fb923c", avatar: "🎯",
    objectives: [
      "Monitor and prioritize the active task queue",
      "Coordinate inter-agent handoffs in real-time",
      "Track task lifecycle from creation to completion",
      "Rebalance workload if agent bottlenecks occur",
    ],
  },
};

function AgentPage() {
  const { agentKey } = useParams();
  const navigate = useNavigate();
  const meta = AGENT_META[agentKey];
  const { micActive, toggleMic, state: convState, levelRef: audioLevelRef, commandLog } = usePageVoice();

  const [status, setStatus] = useState("idle");

  const fetchStatus = useCallback(async () => {
    try {
      const r = await fetch(`${API}/agents/status`);
      if (r.ok) {
        const data = await r.json();
        const found = (data.agents || []).find(
          (a) => a.name.toLowerCase() === agentKey
        );
        if (found) setStatus(found.status);
      }
    } catch {}
  }, [agentKey]);

  useEffect(() => {
    fetchStatus();
    const id = setInterval(fetchStatus, 3000);
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

  if (!meta) {
    return (
      <div className="agent-page-root">
        <div className="agent-page-error">
          <h2>AGENT NOT FOUND</h2>
          <button className="ap-back-btn" onClick={() => navigate("/console")}>
            ← RETURN TO COMMAND CENTER
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="agent-page-root">
      {/* full-screen orb background — same as Phase 2 */}
      <div className="ap-orb-bg">
        <OrbErrorBoundary>
          <Canvas camera={{ position: [0, 0, 4.2], fov: 45 }}
            dpr={[1, 1.5]} gl={{ antialias: true, alpha: true, premultipliedAlpha: false }}>
            <CosmicBackground />
            <CosmicOrb mouseRef={mouseRef} audioLevelRef={audioLevelRef} />
            <EffectComposer>
              <Bloom luminanceThreshold={0.7} luminanceSmoothing={0.95}
                intensity={0.6} radius={0.5} />
              <ChromaticAberration offset={new Vector2(0.0012, 0.0012)}
                radialModulation={false} modulationOffset={0} />
            </EffectComposer>
          </Canvas>
        </OrbErrorBoundary>
      </div>

      <div className="ap-grid-overlay" />

      {/* top bar */}
      <header className="ap-topbar">
        <button className="ap-back-btn" onClick={() => navigate("/console")}>
          ← COMMAND CENTER
        </button>
        <div className="ap-topbar-title" style={{ color: meta.color, textShadow: `0 0 8px ${meta.color}, 0 0 20px ${meta.color}44` }}>{meta.name.toUpperCase()}</div>
        <div className="ap-topbar-right">
          <span className="ap-council-link" onClick={() => navigate("/council")}>
            ◆ COUNCIL VIEW
          </span>
          <LiveClock />
        </div>
      </header>

      {/* LEFT PANEL — agent identity + objectives (roster style) */}
      <div className="ap-left-panel">
        <div className="ap-panel-frame">
          <div className="ap-section-label" style={{ borderColor: meta.color }}>◆ AGENT PROFILE</div>
          <div className="ap-profile-row">
            <span className="ap-avatar">{meta.avatar}</span>
            <div>
              <div className="ap-agent-name" style={{ color: meta.color }}>{meta.name}</div>
              <div className="ap-agent-role">{meta.role}</div>
            </div>
            <span className="ap-status-dot" style={{
              background: status === "working" ? "#e8b15a" : status === "idle" ? "#8fa0b5" : "#00ff88"
            }} />
          </div>
          <div className="ap-agent-desc">{meta.desc}</div>
        </div>

        <div className="ap-panel-frame">
          <div className="ap-section-label" style={{ borderColor: meta.color }}>◆ OBJECTIVES</div>
          {meta.objectives.map((obj, i) => (
            <div key={i} className="ap-objective-row">
              <span className="ap-obj-marker" style={{ color: meta.color }}>▸</span>
              <span className="ap-obj-text">{obj}</span>
            </div>
          ))}
        </div>
      </div>

      {/* RIGHT PANEL — live stats (system parameters style) */}
      <div className="ap-right-panel">
        <div className="ap-panel-frame">
          <div className="ap-section-label" style={{ borderColor: meta.color }}>◆ SYSTEM STATUS</div>
          <div className="ap-param-row">
            <span className="ap-param-key">STATUS</span>
            <span className="ap-param-val" style={{
              color: status === "working" ? "#e8b15a" : status === "idle" ? "#8fa0b5" : "#00ff88"
            }}>{status.toUpperCase()}</span>
          </div>
          <div className="ap-param-row">
            <span className="ap-param-key">AGENT KEY</span>
            <span className="ap-param-val">{agentKey}</span>
          </div>
          <div className="ap-param-row">
            <span className="ap-param-key">ROLE</span>
            <span className="ap-param-val">{meta.role}</span>
          </div>
          <div className="ap-param-row">
            <span className="ap-param-key">OBJECTIVES</span>
            <span className="ap-param-val">{meta.objectives.length} active</span>
          </div>
          <div className="ap-param-row ap-param-row-last">
            <span className="ap-param-key">COLOR</span>
            <span className="ap-param-val" style={{ color: meta.color }}>{meta.color}</span>
          </div>
        </div>
      </div>

      <CommandLog commandLog={commandLog} agentColor={meta.color} />

      <VoiceControls micActive={micActive} toggleMic={toggleMic} convState={convState} />
    </div>
  );
}

export default AgentPage;

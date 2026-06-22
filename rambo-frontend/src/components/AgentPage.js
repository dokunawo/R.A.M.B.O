import React, { useState, useEffect, useCallback, useRef, Component } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Canvas } from "@react-three/fiber";
import { EffectComposer, Bloom, ChromaticAberration } from "@react-three/postprocessing";
import { Vector2 } from "three";
import CosmicOrb from "./CosmicOrb";
import CosmicBackground from "./CosmicBackground";
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

  const [status, setStatus] = useState("idle");
  const [agentDetail, setAgentDetail] = useState(null);
  const [approvals, setApprovals] = useState([]);

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

  const fetchDetail = useCallback(async () => {
    try {
      const r = await fetch(`${API}/agents/${agentKey}/detail`);
      if (r.ok) setAgentDetail(await r.json());
    } catch {}
  }, [agentKey]);

  const fetchApprovals = useCallback(async () => {
    if (agentKey !== "sentinel") return;
    try {
      const r = await fetch(`${API}/sentinel/approvals`);
      if (r.ok) setApprovals(await r.json());
    } catch {}
  }, [agentKey]);

  useEffect(() => {
    fetchStatus();
    fetchDetail();
    fetchApprovals();
    const id = setInterval(() => {
      fetchStatus();
      fetchDetail();
      fetchApprovals();
    }, 3000);
    return () => clearInterval(id);
  }, [fetchStatus, fetchDetail, fetchApprovals]);

  const handleDecision = async (approvalId, decision) => {
    try {
      await fetch(`${API}/sentinel/decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: approvalId, decision }),
      });
      fetchApprovals();
    } catch {}
  };

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

  const detail = agentDetail || {};
  const tasksCompleted = detail.tasks_completed ?? 0;
  const tasksPending = detail.tasks_pending ?? 0;
  const successRate = detail.success_rate ?? "100%";
  const recentActivity = detail.recent_activity ?? [];
  const budgetData = detail.budget ?? null;

  return (
    <div className="agent-page-root">
      {/* full-screen orb background — same as Phase 2 */}
      <div className="ap-orb-bg">
        <OrbErrorBoundary>
          <Canvas camera={{ position: [0, 0, 4.2], fov: 45 }}
            dpr={[1, 1.5]} gl={{ antialias: true, alpha: true, premultipliedAlpha: false }}>
            <CosmicBackground />
            <CosmicOrb mouseRef={mouseRef} />
            <EffectComposer>
              <Bloom luminanceThreshold={0.4} luminanceSmoothing={0.9}
                intensity={1.4} radius={0.8} />
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
        <div className="ap-topbar-title">{meta.name.toUpperCase()}</div>
        <div className="ap-topbar-right">
          <span className="ap-council-link" onClick={() => navigate("/council")}>
            ◆ COUNCIL VIEW
          </span>
          <LiveClock />
        </div>
      </header>

      {/* orb hero with avatar */}
      <section className="ap-orb-hero">
        <div className="ap-avatar-overlay" style={{ borderColor: meta.color }}>
          <span className="ap-avatar-icon">{meta.avatar}</span>
        </div>
        <div className="ap-orb-labels">
          <span className="ap-orb-label-top">Incoming Contacts</span>
          <span className="ap-orb-label-right">Outgoing Dispatch</span>
          <span className="ap-orb-label-bottom">Active Operations</span>
        </div>
      </section>

      {/* agent info card */}
      <section className="ap-info-card" style={{ borderColor: meta.color }}>
        <div className="ap-info-left">
          <div
            className="ap-avatar-badge"
            style={{ background: meta.color + "22", borderColor: meta.color }}
          >
            <span>{meta.avatar}</span>
          </div>
          <div className="ap-info-text">
            <h2 className="ap-agent-name" style={{ color: meta.color }}>
              {meta.name.toUpperCase()}
            </h2>
            <p className="ap-agent-role">{meta.role}</p>
            <p className="ap-agent-desc">{meta.desc}</p>
          </div>
        </div>
        <div className="ap-status-pill" style={{
          background: status === "working" ? "#e8b15a33" : status === "idle" ? "#8fa0b522" : "#00ff8833",
          color: status === "working" ? "#e8b15a" : status === "idle" ? "#8fa0b5" : "#00ff88",
          borderColor: status === "working" ? "#e8b15a" : status === "idle" ? "#8fa0b5" : "#00ff88",
        }}>
          {status.toUpperCase()}
        </div>
      </section>

      {/* stat cards */}
      <section className="ap-stats-row">
        <div className="ap-stat-card" style={{ borderBottomColor: meta.color }}>
          <span className="ap-stat-value" style={{ color: meta.color }}>
            {tasksCompleted}
          </span>
          <span className="ap-stat-label">Tasks Completed</span>
        </div>
        <div className="ap-stat-card" style={{ borderBottomColor: meta.color }}>
          <span className="ap-stat-value" style={{ color: meta.color }}>
            {tasksPending}
          </span>
          <span className="ap-stat-label">Tasks Pending</span>
        </div>
        <div className="ap-stat-card" style={{ borderBottomColor: meta.color }}>
          <span className="ap-stat-value" style={{ color: meta.color }}>
            {successRate}
          </span>
          <span className="ap-stat-label">Success Rate</span>
        </div>
      </section>

      {/* core objectives */}
      <section className="ap-section">
        <h3 className="ap-section-title" style={{ color: meta.color }}>
          ◆ CORE OBJECTIVES
        </h3>
        <ul className="ap-objectives">
          {meta.objectives.map((obj, i) => (
            <li key={i} className="ap-objective-row">
              <div className="ap-obj-text">{obj}</div>
              <div className="ap-obj-bar">
                <div
                  className="ap-obj-fill"
                  style={{
                    width: `${70 + Math.random() * 30}%`,
                    background: meta.color,
                  }}
                />
              </div>
            </li>
          ))}
        </ul>
      </section>

      {/* recent activity */}
      <section className="ap-section">
        <h3 className="ap-section-title" style={{ color: meta.color }}>
          ◆ RECENT ACTIVITY
        </h3>
        {recentActivity.length === 0 ? (
          <p className="ap-empty">No recent activity recorded.</p>
        ) : (
          <ul className="ap-activity-list">
            {recentActivity.map((item, i) => (
              <li key={i} className="ap-activity-item">
                <span className="ap-activity-time">{item.time}</span>
                <span className="ap-activity-text">{item.text}</span>
                <span className={`ap-activity-status ap-status-${item.status}`}>
                  {item.status}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* sentinel approval queue */}
      {agentKey === "sentinel" && (
        <section className="ap-section ap-sentinel-section">
          <h3 className="ap-section-title" style={{ color: meta.color }}>
            ◆ SENTINEL APPROVAL QUEUE
          </h3>
          <p className="ap-sentinel-desc">
            Review and approve or deny agent operations. All risky operations
            require explicit clearance before execution.
          </p>
          {approvals.length === 0 ? (
            <p className="ap-empty">No pending approvals.</p>
          ) : (
            <ul className="ap-approval-list">
              {approvals.map((a) => (
                <li key={a.id} className="ap-approval-item">
                  <div className="ap-approval-info">
                    <span className="ap-approval-agent">{a.agent}</span>
                    <span className="ap-approval-desc">{a.description}</span>
                  </div>
                  <div className="ap-approval-actions">
                    <button
                      className="ap-btn ap-btn-approve"
                      onClick={() => handleDecision(a.id, "APPROVE")}
                    >
                      APPROVE
                    </button>
                    <button
                      className="ap-btn ap-btn-deny"
                      onClick={() => handleDecision(a.id, "DENY")}
                    >
                      DENY
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {/* steward budget planner */}
      {agentKey === "steward" && (
        <section className="ap-section ap-steward-section">
          <h3 className="ap-section-title" style={{ color: meta.color }}>
            ◆ BUDGET PLANNER
          </h3>
          {budgetData ? (
            <div className="ap-budget">
              <table className="ap-budget-table">
                <thead>
                  <tr>
                    <th>Category</th>
                    <th>Budgeted</th>
                    <th>Spent</th>
                    <th>Remaining</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {(budgetData.categories || []).map((cat, i) => {
                    const remaining = cat.budgeted - cat.spent;
                    const pct = cat.budgeted > 0 ? (cat.spent / cat.budgeted) * 100 : 0;
                    return (
                      <tr key={i}>
                        <td>{cat.name}</td>
                        <td className="ap-budget-num">${cat.budgeted.toFixed(2)}</td>
                        <td className="ap-budget-num">${cat.spent.toFixed(2)}</td>
                        <td className="ap-budget-num" style={{
                          color: remaining < 0 ? "#ff4466" : "#22c55e",
                        }}>
                          ${remaining.toFixed(2)}
                        </td>
                        <td>
                          <div className="ap-budget-bar">
                            <div
                              className="ap-budget-fill"
                              style={{
                                width: `${Math.min(pct, 100)}%`,
                                background: pct > 90 ? "#ff4466" : pct > 70 ? "#e8b15a" : "#22c55e",
                              }}
                            />
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {budgetData.total_budget != null && (
                <div className="ap-budget-summary">
                  <span>Total Budget: <b>${budgetData.total_budget.toFixed(2)}</b></span>
                  <span>Total Spent: <b>${budgetData.total_spent.toFixed(2)}</b></span>
                  <span style={{
                    color: budgetData.total_budget - budgetData.total_spent < 0 ? "#ff4466" : "#22c55e",
                  }}>
                    Remaining: <b>${(budgetData.total_budget - budgetData.total_spent).toFixed(2)}</b>
                  </span>
                </div>
              )}
            </div>
          ) : (
            <p className="ap-empty">No budget data available. Configure via Steward agent.</p>
          )}
        </section>
      )}

      {/* footer */}
      <footer className="ap-footer">
        <span>R.A.M.B.O — Accuracy · Precision · Execution</span>
        <span>© {new Date().getFullYear()}</span>
      </footer>
    </div>
  );
}

export default AgentPage;

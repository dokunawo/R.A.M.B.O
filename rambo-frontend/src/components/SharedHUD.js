import React, { useState, useEffect, useRef, useCallback } from "react";
import { audioRunning, isMuted, resumeAudio } from "./audioEngine";
import "./SharedHUD.css";

const API = "http://localhost:8000";
const WS_URL = "ws://localhost:8000/ws/activity";

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

export function useSystemStats() {
  const [stats, setStats] = useState(null);
  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const r = await fetch(`${API}/system/stats`);
        if (r.ok && !cancelled) setStats(await r.json());
      } catch {}
    };
    poll();
    const id = setInterval(poll, 3000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);
  return stats;
}

export function useActivityFeed() {
  const [activity, setActivity] = useState([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let ws;
    let closed = false;
    let retry;
    const connect = () => {
      try { ws = new WebSocket(WS_URL); } catch { return; }
      ws.onopen = () => setConnected(true);
      ws.onclose = () => { setConnected(false); if (!closed) retry = setTimeout(connect, 2500); };
      ws.onerror = () => { try { ws.close(); } catch {} };
      ws.onmessage = (e) => {
        const msg = String(e.data);
        if (msg.charAt(0) === "{") return;
        if (/^STATUS:/.test(msg)) return;
        setActivity(prev => [...prev, { id: `${Date.now()}-${Math.random()}`, msg }].slice(-120));
      };
    };
    connect();
    return () => { closed = true; clearTimeout(retry); if (ws) try { ws.close(); } catch {} };
  }, []);

  return { activity, connected };
}

export function StatBars({ stats }) {
  const bars = stats?.available
    ? [
        { label: "CPU", value: stats.cpu_percent, displayValue: `${Math.round(stats.cpu_percent)}%` },
        { label: "RAM", value: stats.ram_percent, displayValue: `${stats.ram_used_gb}G` },
        { label: "DSK", value: stats.disk_percent, displayValue: `${stats.disk_used_gb}G` },
      ]
    : [
        { label: "CPU", value: 0, displayValue: "—" },
        { label: "RAM", value: 0, displayValue: "—" },
        { label: "DSK", value: 0, displayValue: "—" },
      ];

  return (
    <div className="hud-stat-panel">
      {bars.map(s => {
        const pct = Math.min(100, (s.value / 100) * 100);
        return (
          <div key={s.label} className="hud-stat-row">
            <span className="hud-stat-label">{s.label}</span>
            <span className="hud-stat-bar">
              <span className="hud-stat-bar-fill" style={{ width: `${pct}%` }} />
            </span>
            <span className="hud-stat-value">{s.displayValue}</span>
          </div>
        );
      })}
    </div>
  );
}

export function useCostDashboard() {
  const [data, setData] = useState(null);
  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      if (document.hidden) return;
      try {
        const r = await fetch(`${API}/usage`);
        if (r.ok && !cancelled) setData(await r.json());
      } catch {}
    };
    poll();
    const id = setInterval(poll, 60000);
    const onVis = () => { if (!document.hidden) poll(); };
    document.addEventListener("visibilitychange", onVis);
    return () => { cancelled = true; clearInterval(id); document.removeEventListener("visibilitychange", onVis); };
  }, []);
  return data;
}

export function CostIndicator({ data }) {
  const [expanded, setExpanded] = useState(false);
  const panelRef = useRef(null);

  useEffect(() => {
    if (!expanded) return;
    const close = (e) => { if (panelRef.current && !panelRef.current.contains(e.target)) setExpanded(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [expanded]);

  if (!data) return null;

  const mtd = data.month_to_date;
  const costStr = mtd.cost_usd < 0.01 && mtd.cost_usd > 0
    ? "<$0.01"
    : `$${mtd.cost_usd.toFixed(2)}`;

  const delta = data.mom_delta_pct;
  const deltaClass = delta > 0 ? "hud-cost-delta-up" : delta < 0 ? "hud-cost-delta-down" : "";
  const deltaStr = delta !== 0 ? `${delta > 0 ? "+" : ""}${delta}%` : "";

  return (
    <div className="hud-cost-wrap" ref={panelRef}>
      <div className="hud-cost-face" onClick={() => setExpanded(e => !e)}>
        <span className="hud-cost-tag">API</span>
        <span className="hud-cost-amount">{costStr}</span>
        {deltaStr && <span className={`hud-cost-delta ${deltaClass}`}>{deltaStr}</span>}
      </div>

      {expanded && (
        <div className="hud-cost-panel">
          <div className="hud-cost-panel-header">◆ COST DASHBOARD</div>

          <div className="hud-cost-section">
            <div className="hud-cost-row">
              <span>Month-to-date</span>
              <span>${mtd.cost_usd.toFixed(4)}</span>
            </div>
            <div className="hud-cost-row">
              <span>Today</span>
              <span>${data.today.cost_usd.toFixed(4)}</span>
            </div>
            <div className="hud-cost-row">
              <span>Calls</span>
              <span>{mtd.call_count}</span>
            </div>
            {data.cache_savings_usd > 0 && (
              <div className="hud-cost-row hud-cost-savings">
                <span>Cache savings</span>
                <span>−${data.cache_savings_usd.toFixed(4)}</span>
              </div>
            )}
          </div>

          {data.by_model.length > 0 && (
            <div className="hud-cost-section">
              <div className="hud-cost-section-label">BY MODEL</div>
              {data.by_model.map(m => (
                <div key={m.model} className="hud-cost-row">
                  <span>{m.model}</span>
                  <span>${m.cost.toFixed(4)} ({m.calls})</span>
                </div>
              ))}
            </div>
          )}

          {data.by_day.length > 0 && (
            <div className="hud-cost-section hud-cost-daily">
              <div className="hud-cost-section-label">DAILY</div>
              {data.by_day.map(d => (
                <div key={d.day} className="hud-cost-row">
                  <span>{d.day}</span>
                  <span>${d.cost.toFixed(4)} ({d.calls})</span>
                </div>
              ))}
            </div>
          )}

          <div className="hud-cost-section">
            <div className="hud-cost-row hud-cost-tokens">
              <span>IN {mtd.input_tokens.toLocaleString()}</span>
              <span>OUT {mtd.output_tokens.toLocaleString()}</span>
            </div>
            {(mtd.cache_write_tokens > 0 || mtd.cache_read_tokens > 0) && (
              <div className="hud-cost-row hud-cost-tokens">
                <span>C/W {mtd.cache_write_tokens.toLocaleString()}</span>
                <span>C/R {mtd.cache_read_tokens.toLocaleString()}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export function useFactoryPending() {
  const [pending, setPending] = useState([]);

  const refresh = useCallback(async () => {
    if (document.hidden) return;
    try {
      const r = await fetch(`${API}/factory/pending`);
      if (r.ok) setPending(await r.json());
    } catch {}
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 15000);
    const onVis = () => { if (!document.hidden) refresh(); };
    document.addEventListener("visibilitychange", onVis);
    return () => { clearInterval(id); document.removeEventListener("visibilitychange", onVis); };
  }, [refresh]);

  return { pending, refresh };
}

function FactoryCard({ task, onResolved }) {
  const [busy, setBusy] = useState(false);
  const [showReject, setShowReject] = useState(false);
  const [feedback, setFeedback] = useState("");
  const m = task.proposed_manifest || {};

  const approve = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await fetch(`${API}/factory/approve/${task.id}`, { method: "POST" });
      onResolved();
    } catch {} finally { setBusy(false); }
  };

  const reject = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await fetch(`${API}/factory/reject/${task.id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ feedback: feedback.trim() || null }),
      });
      setShowReject(false);
      setFeedback("");
      onResolved();
    } catch {} finally { setBusy(false); }
  };

  return (
    <div className="hud-factory-card">
      <div className="hud-factory-card-head">
        <span className="hud-factory-name">{m.name || task.name_hint}</span>
        <span className="hud-factory-slug">{m.slug}</span>
      </div>
      <div className="hud-factory-specialty">{m.specialty || task.role_description}</div>
      {m.tool_allowlist && m.tool_allowlist.length > 0 && (
        <div className="hud-factory-tools">
          {m.tool_allowlist.map(t => <span key={t} className="hud-factory-tool">{t}</span>)}
        </div>
      )}
      {m.system_prompt && (
        <div className="hud-factory-prompt">{m.system_prompt.slice(0, 240)}{m.system_prompt.length > 240 ? "…" : ""}</div>
      )}
      {task.approval_iterations > 0 && (
        <div className="hud-factory-iter">revision {task.approval_iterations}</div>
      )}

      {!showReject ? (
        <div className="hud-factory-actions">
          <button className="hud-factory-approve" onClick={approve} disabled={busy}>
            {busy ? "…" : "APPROVE"}
          </button>
          <button className="hud-factory-reject" onClick={() => setShowReject(true)} disabled={busy}>
            REJECT
          </button>
        </div>
      ) : (
        <div className="hud-factory-reject-box">
          <input
            className="hud-factory-feedback"
            type="text"
            value={feedback}
            onChange={e => setFeedback(e.target.value)}
            placeholder="Feedback (blank = kill task)"
            spellCheck={false}
          />
          <div className="hud-factory-actions">
            <button className="hud-factory-reject" onClick={reject} disabled={busy}>
              {feedback.trim() ? "REVISE" : "KILL"}
            </button>
            <button className="hud-factory-cancel" onClick={() => setShowReject(false)} disabled={busy}>
              CANCEL
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export function FactoryDock({ pending, onRefresh }) {
  const [open, setOpen] = useState(false);
  if (!pending) return null;

  return (
    <div className="hud-factory-wrap">
      <div className="hud-factory-face" onClick={() => setOpen(o => !o)}>
        <span className="hud-factory-tag">FACTORY</span>
        <span className="hud-factory-count">{pending.length}</span>
      </div>
      {open && (
        <div className="hud-factory-panel">
          <div className="hud-factory-panel-header">◆ PENDING AGENTS</div>
          {pending.length === 0
            ? <div className="hud-factory-empty">{"// no agents awaiting approval"}</div>
            : pending.map(t => (
                <FactoryCard key={t.id} task={t} onResolved={onRefresh} />
              ))}
        </div>
      )}
    </div>
  );
}

// ── Tier 4: confirmation gate dock ──────────────────────────────

function usePolledQueue(path, interval = 12000) {
  const [items, setItems] = useState([]);
  const refresh = useCallback(async () => {
    if (document.hidden) return;
    try {
      const r = await fetch(`${API}${path}`);
      if (r.ok) setItems(await r.json());
    } catch {}
  }, [path]);
  useEffect(() => {
    refresh();
    const id = setInterval(refresh, interval);
    const onVis = () => { if (!document.hidden) refresh(); };
    document.addEventListener("visibilitychange", onVis);
    return () => { clearInterval(id); document.removeEventListener("visibilitychange", onVis); };
  }, [refresh, interval]);
  return { items, refresh };
}

async function _post(path, refresh) {
  try { await fetch(`${API}${path}`, { method: "POST" }); } catch {}
  refresh();
}

export function ConfirmationDock() {
  const { items, refresh } = usePolledQueue("/confirmations");
  const [open, setOpen] = useState(false);

  return (
    <div className="hud-confirm-wrap">
      <div className="hud-factory-face" onClick={() => setOpen(o => !o)}>
        <span className="hud-confirm-tag">CONFIRM</span>
        <span className={`hud-factory-count ${items.length ? "hud-count-hot" : ""}`}>{items.length}</span>
      </div>
      {open && (
        <div className="hud-factory-panel">
          <div className="hud-factory-panel-header">◆ ACTIONS AWAITING APPROVAL</div>
          {items.length === 0
            ? <div className="hud-factory-empty">{"// no actions awaiting approval"}</div>
            : items.map(c => (
                <div key={c.id} className="hud-factory-card">
                  <div className="hud-factory-card-head">
                    <span className="hud-factory-name">{c.tool_name}</span>
                    {c.agent_slug && <span className="hud-factory-slug">{c.agent_slug}</span>}
                  </div>
                  <div className="hud-factory-prompt">{JSON.stringify(c.tool_input)}</div>
                  <div className="hud-factory-actions">
                    <button className="hud-factory-approve" onClick={() => _post(`/confirmations/${c.id}/approve`, refresh)}>APPROVE</button>
                    <button className="hud-factory-reject" onClick={() => _post(`/confirmations/${c.id}/reject`, refresh)}>REJECT</button>
                  </div>
                </div>
              ))}
        </div>
      )}
    </div>
  );
}

// ── Tier 5: handoff dock ────────────────────────────────────────

export function HandoffDock() {
  const { items, refresh } = usePolledQueue("/handoffs");
  const [open, setOpen] = useState(false);

  const confidenceLabel = (c) =>
    c >= 0.75 ? "high" : c >= 0.4 ? "medium" : "low";

  return (
    <div className="hud-handoff-wrap">
      <div className="hud-factory-face" onClick={() => setOpen(o => !o)}>
        <span className="hud-handoff-tag">HANDOFF</span>
        <span className={`hud-factory-count ${items.length ? "hud-count-hot" : ""}`}>{items.length}</span>
      </div>
      {open && (
        <div className="hud-factory-panel">
          <div className="hud-factory-panel-header">◆ PROPOSED HANDOFFS</div>
          {items.length === 0
            ? <div className="hud-factory-empty">{"// no handoffs proposed"}</div>
            : items.map(h => (
                <div key={h.id} className="hud-factory-card">
                  <div className="hud-factory-card-head">
                    <span className="hud-factory-name">→ {h.target_agent}</span>
                    <span className="hud-factory-slug">{confidenceLabel(h.confidence)} ({Math.round(h.confidence * 100)}%)</span>
                  </div>
                  {h.from_agent && <div className="hud-factory-slug">from {h.from_agent}</div>}
                  <div className="hud-factory-specialty">{h.reason}</div>
                  <div className="hud-factory-prompt">{h.task}</div>
                  {h.preconditions && h.preconditions.length > 0 && (
                    <div className="hud-factory-tools">
                      {h.preconditions.map((p, i) => <span key={i} className="hud-factory-tool">⚠ {p}</span>)}
                    </div>
                  )}
                  {h.artifacts && Object.keys(h.artifacts).length > 0 && (
                    <div className="hud-factory-tools">
                      {Object.entries(h.artifacts).map(([k, v]) => <span key={k} className="hud-factory-tool">{k}: {v}</span>)}
                    </div>
                  )}
                  <div className="hud-factory-actions">
                    <button className="hud-factory-approve" onClick={() => _post(`/handoffs/${h.id}/accept`, refresh)}>ACCEPT</button>
                    <button className="hud-factory-reject" onClick={() => _post(`/handoffs/${h.id}/reject`, refresh)}>REJECT</button>
                  </div>
                </div>
              ))}
        </div>
      )}
    </div>
  );
}

// Fallback for when the browser blocked autoplay (e.g. the tab opened without a
// gesture, or Chrome was already running so the --autoplay-policy flag didn't
// apply). Shows a pill while audio is locked; one click unlocks it and it hides.
export function SoundGate() {
  const [needed, setNeeded] = useState(false);

  useEffect(() => {
    const check = () => setNeeded(!audioRunning() && !isMuted());
    check();
    const id = setInterval(check, 1000);
    return () => clearInterval(id);
  }, []);

  if (!needed) return null;

  const enable = () => {
    resumeAudio();                         // this click is the user gesture
    setTimeout(() => setNeeded(!audioRunning() && !isMuted()), 300);
  };

  return (
    <button className="hud-soundgate" type="button" onClick={enable}
      title="Audio is blocked by the browser — click to enable">
      <span className="hud-soundgate-icon">🔊</span> ENABLE SOUND
    </button>
  );
}

export function ActivityFeed({ activity }) {
  const feedRef = useRef(null);
  useEffect(() => {
    if (feedRef.current) feedRef.current.scrollTop = feedRef.current.scrollHeight;
  }, [activity]);
  return (
    <div className="hud-activity-feed" ref={feedRef} aria-live="polite">
      <div className="hud-activity-label">◆ ACTIVITY FEED</div>
      {activity.length === 0
        ? <div className="hud-feed-empty">{"// awaiting activity…"}</div>
        : activity.map(a => <div key={a.id} className="hud-feed-line">{a.msg}</div>)}
    </div>
  );
}

export function CommandInput({ connected }) {
  const [goal, setGoal] = useState("");
  const [busy, setBusy] = useState(false);
  const locRef = useRef({ lat: null, lon: null });

  useEffect(() => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (pos) => { locRef.current = { lat: pos.coords.latitude, lon: pos.coords.longitude }; },
      () => {},
      { timeout: 8000, maximumAge: 600000 },
    );
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    const g = goal.trim();
    if (!g || busy) return;
    setBusy(true);
    try {
      await fetch(`${API}/rambo/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal: g, lat: locRef.current.lat, lon: locRef.current.lon }),
      });
      setGoal("");
    } catch {} finally { setBusy(false); }
  };

  return (
    <div className="hud-cmd-input">
      <form className="hud-cmd-row" onSubmit={submit}>
        <span className={`hud-cmd-conn ${connected ? "on" : "off"}`}>
          {connected ? "● LIVE" : "○ OFFLINE"}
        </span>
        <span className="hud-cmd-prompt">&gt;</span>
        <input
          className="hud-cmd-field"
          type="text"
          value={goal}
          onChange={e => setGoal(e.target.value)}
          placeholder="Issue a directive to R.A.M.B.O…"
          spellCheck={false}
          autoComplete="off"
        />
        <button className="hud-cmd-exec" type="submit" disabled={busy || !goal.trim()}>
          {busy ? "RUNNING…" : "EXECUTE"}
        </button>
      </form>
    </div>
  );
}

import React, { useState, useEffect, useRef, useCallback } from "react";
import { audioRunning, isMuted, resumeAudio, getVolume, setVolume } from "./audioEngine";
import { startShare, stopShare, isSharing, onShareChange, frameForGoal, armAutoStart } from "./screenVision";
import "./SharedHUD.css";

const API = "http://localhost:8000";
const WS_URL = "ws://localhost:8000/ws/activity";

// Accordion store for the left-rail docks: only one panel open at a time, shared
// across every page with no prop drilling. A dock calls useDockOpen(id) to get
// [isOpen, toggle]; toggling one closes whichever other was open.
let _openDock = null;
const _openDockListeners = new Set();
function useDockOpen(id) {
  const [, force] = useState(0);
  useEffect(() => {
    const fn = () => force(n => n + 1);
    _openDockListeners.add(fn);
    return () => { _openDockListeners.delete(fn); };
  }, []);
  const toggle = useCallback(() => {
    _openDock = _openDock === id ? null : id;
    _openDockListeners.forEach(fn => fn());
  }, [id]);
  return [_openDock === id, toggle];
}

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

// Tracks the current Engineer task (build or self-edit) from the WS progress
// events and produces a smoothly-advancing progress value + ETA countdown. The
// bar always creeps forward with time AND jumps at each stage, but only reaches
// 100% on the real completion event ("ready") — i.e. when it's actually created.
export function useTaskProgress() {
  const [view, setView] = useState(null);
  const ref = useRef(null);

  useEffect(() => {
    let ws, closed = false, retry;
    const connect = () => {
      try { ws = new WebSocket(WS_URL); } catch { return; }
      ws.onclose = () => { if (!closed) retry = setTimeout(connect, 2500); };
      ws.onerror = () => { try { ws.close(); } catch {} };
      ws.onmessage = (e) => {
        const msg = String(e.data);
        if (msg.charAt(0) !== "{") return;
        let j; try { j = JSON.parse(msg); } catch { return; }
        if (j.t !== "build_progress" && j.t !== "dev_progress") return;
        const id = j.slug || j.id || "task";
        const isBuild = j.t === "build_progress";
        let s = ref.current;
        if (!s || s.id !== id || s.finished) {
          s = ref.current = { id, label: isBuild ? "Building" : "Drafting",
            etaS: j.eta_s || 60, startedAt: Date.now(), target: 5, pct: 0, finished: false };
        }
        if (j.eta_s) s.etaS = j.eta_s;
        switch (j.stage) {
          case "coding": s.target = Math.max(s.target, 15); break;
          case "tool":   s.target = Math.min(85, Math.max(s.target, 15) + 4); break;
          case "impact": s.target = Math.max(s.target, 88); break;
          case "commit": s.target = Math.max(s.target, 92); break;
          case "ready":  s.target = 100; s.finished = true; s.finishedAt = Date.now(); break;
          default: break;
        }
      };
    };
    connect();
    const anim = setInterval(() => {
      const s = ref.current;
      if (!s) return;
      const elapsed = (Date.now() - s.startedAt) / 1000;
      const timeEst = Math.min(94, (elapsed / Math.max(1, s.etaS)) * 100);
      const target = s.finished ? 100 : Math.max(s.target, timeEst);
      s.pct += (target - s.pct) * 0.16;
      if (s.finished && s.pct > 99.3) s.pct = 100;
      if (s.finished && s.finishedAt && Date.now() - s.finishedAt > 4500) {
        ref.current = null; setView(null); return;
      }
      setView({ label: s.label, pct: s.pct, etaS: s.etaS, elapsed, finished: s.finished });
    }, 120);
    return () => { closed = true; clearTimeout(retry); clearInterval(anim); if (ws) try { ws.close(); } catch {} };
  }, []);

  return view;
}

export function ActiveTaskBar() {
  const task = useTaskProgress();
  if (!task) return null;
  const pct = Math.min(100, Math.round(task.pct));
  const remain = Math.max(0, Math.round(task.etaS - task.elapsed));
  const status = task.finished ? "FINISHED ✓" : remain > 0 ? `~${remain}s left` : "finalizing…";
  return (
    <div className="hud-task-bar">
      <div className="hud-task-head">
        <span className="hud-task-label">ENGINEER · {task.finished ? "DONE" : task.label.toUpperCase()}</span>
        <span className="hud-task-eta">{pct}% · {status}</span>
      </div>
      <div className="hud-task-track">
        <div className={`hud-task-fill ${task.finished ? "hud-task-fill-done" : ""}`} style={{ width: pct + "%" }} />
      </div>
    </div>
  );
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

/* ---- ElevenLabs voice-credit tracker ---- */

function formatK(n) {
  if (n == null) return "—";
  if (n >= 1000) {
    const k = n / 1000;
    return `${k % 1 === 0 ? k.toFixed(0) : k.toFixed(1)}k`;
  }
  return `${n}`;
}

export function useElevenLabsUsage() {
  const [data, setData] = useState(null);
  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      if (document.hidden) return;
      try {
        const r = await fetch(`${API}/usage/tts`);
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

export function VoiceCostIndicator({ data }) {
  const [expanded, setExpanded] = useState(false);
  const panelRef = useRef(null);

  useEffect(() => {
    if (!expanded) return;
    const close = (e) => { if (panelRef.current && !panelRef.current.contains(e.target)) setExpanded(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [expanded]);

  if (!data) return null;

  const block = data.real ?? data.local;
  if (!block) return null;
  const sourceTag = data.source === "real" ? "REAL" : "LIVE";

  return (
    <div className="hud-cost-wrap" ref={panelRef}>
      <div className="hud-cost-face" onClick={() => setExpanded(e => !e)}>
        <span className="hud-cost-tag">VOICE</span>
        <span className="hud-cost-amount">{formatK(block.remaining)}</span>
        <span className="hud-cost-delta">{formatK(block.used)}/{formatK(block.limit)}</span>
        <span className="hud-voice-src">{sourceTag}</span>
      </div>

      {expanded && (
        <div className="hud-cost-panel">
          <div className="hud-cost-panel-header">◆ VOICE CREDITS</div>
          <div className="hud-cost-section">
            <div className="hud-cost-row"><span>Remaining</span><span>{block.remaining.toLocaleString()}</span></div>
            <div className="hud-cost-row"><span>Used</span><span>{block.used.toLocaleString()}</span></div>
            <div className="hud-cost-row"><span>Limit</span><span>{block.limit.toLocaleString()}</span></div>
            <div className="hud-cost-row"><span>Resets</span><span>{data.reset_date}</span></div>
            <div className="hud-cost-row"><span>Source</span><span>{data.source === "real" ? "ElevenLabs" : "Local count"}</span></div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ---- Voyage embedding-credit tracker ---- */

function formatTokens(n) {
  if (n == null) return "—";
  if (n >= 1_000_000) {
    const m = n / 1_000_000;
    return `${m % 1 === 0 ? m.toFixed(0) : m.toFixed(1)}M`;
  }
  return formatK(n);
}

export function useVoyageUsage() {
  const [data, setData] = useState(null);
  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      if (document.hidden) return;
      try {
        const r = await fetch(`${API}/usage/embed`);
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

export function EmbedCostIndicator({ data }) {
  const [expanded, setExpanded] = useState(false);
  const panelRef = useRef(null);

  useEffect(() => {
    if (!expanded) return;
    const close = (e) => { if (panelRef.current && !panelRef.current.contains(e.target)) setExpanded(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [expanded]);

  if (!data || !data.tokens) return null;
  const t = data.tokens;
  const credit = data.credit || {};

  return (
    <div className="hud-cost-wrap" ref={panelRef}>
      <div className="hud-cost-face" onClick={() => setExpanded(e => !e)}>
        <span className="hud-cost-tag">EMBED</span>
        <span className="hud-cost-amount">{formatTokens(t.remaining)}</span>
        <span className="hud-cost-delta">{formatTokens(t.used)}/{formatTokens(t.limit)}</span>
        <span className="hud-voice-src">{data.active ? "ON" : "OFF"}</span>
      </div>

      {expanded && (
        <div className="hud-cost-panel">
          <div className="hud-cost-panel-header">◆ EMBED CREDITS</div>
          <div className="hud-cost-section">
            <div className="hud-cost-row"><span>Free remaining</span><span>{t.remaining.toLocaleString()}</span></div>
            <div className="hud-cost-row"><span>Free used</span><span>{t.used.toLocaleString()}</span></div>
            <div className="hud-cost-row"><span>Free limit</span><span>{t.limit.toLocaleString()}</span></div>
          </div>
          <div className="hud-cost-section">
            <div className="hud-cost-row"><span>Paid balance</span><span>${(credit.remaining_usd ?? 0).toFixed(2)}</span></div>
            <div className="hud-cost-row"><span>Paid spent</span><span>${(credit.spent_usd ?? 0).toFixed(4)}</span></div>
          </div>
          <div className="hud-cost-section">
            <div className="hud-cost-row"><span>MTD tokens</span><span>{(data.month_to_date?.tokens ?? 0).toLocaleString()}</span></div>
            <div className="hud-cost-row"><span>MTD calls</span><span>{data.month_to_date?.calls ?? 0}</span></div>
            <div className="hud-cost-row"><span>Model</span><span>{data.model}</span></div>
            <div className="hud-cost-row"><span>Status</span><span>{data.active ? "Active" : "Key not set"}</span></div>
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
  const [open, toggle] = useDockOpen("factory");
  if (!pending) return null;

  return (
    <div className="hud-factory-wrap">
      <div className="hud-factory-face" onClick={toggle}>
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

// Ask the host helper (rambo-mediakeys.ahk) to open a folder on the desktop.
async function openOnDesktop(hostPath) {
  try {
    await fetch(`${API}/desktop/open`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: hostPath }),
    });
  } catch {}
}

export function ConfirmationDock() {
  const { items, refresh } = usePolledQueue("/confirmations");
  const [open, toggle] = useDockOpen("confirm");

  return (
    <div className="hud-confirm-wrap">
      <div className="hud-factory-face" onClick={toggle}>
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
  const [open, toggle] = useDockOpen("handoff");

  const confidenceLabel = (c) =>
    c >= 0.75 ? "high" : c >= 0.4 ? "medium" : "low";

  return (
    <div className="hud-handoff-wrap">
      <div className="hud-factory-face" onClick={toggle}>
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

// ── Self-coding: code review dock ───────────────────────────────
// RAMBO's proposed self-changes. Each card shows the recommendation, what the
// change affects, and (on expand) the full diff — with Merge / Send to Claude /
// Reject. Merge lands the branch on the base branch; nothing goes live until the
// backend restarts (no auto-reload).

const REC_LABEL = { merge: "SAFE TO MERGE", escalate: "ASK CLAUDE", hold: "HOLD" };

function DevReviewCard({ change, onResolved }) {
  const [busy, setBusy] = useState(false);
  const [detail, setDetail] = useState(null);
  const [showDiff, setShowDiff] = useState(false);
  const impact = change.impact || {};
  const rec = impact.recommendation || change.recommendation || "escalate";

  const loadDiff = async () => {
    if (showDiff) { setShowDiff(false); return; }
    if (!detail) {
      try {
        const r = await fetch(`${API}/dev/change/${change.id}`);
        if (r.ok) setDetail(await r.json());
      } catch {}
    }
    setShowDiff(true);
  };

  const act = async (verb) => {
    if (busy) return;
    setBusy(true);
    try { await fetch(`${API}/dev/${verb}/${change.id}`, { method: "POST" }); onResolved(); }
    catch {} finally { setBusy(false); }
  };

  return (
    <div className="hud-factory-card">
      <div className="hud-factory-card-head">
        <span className="hud-factory-name">{change.goal.slice(0, 60)}{change.goal.length > 60 ? "…" : ""}</span>
        <span className={`hud-dev-rec hud-dev-rec-${rec}`}>{REC_LABEL[rec] || rec}</span>
      </div>
      {impact.summary && <div className="hud-factory-specialty">{impact.summary}</div>}
      {impact.affects && impact.affects.length > 0 && (
        <div className="hud-factory-tools">
          {impact.affects.map((a, i) => <span key={i} className="hud-factory-tool">{a}</span>)}
        </div>
      )}
      {impact.rationale && <div className="hud-factory-iter">risk: {impact.risk} — {impact.rationale}</div>}

      <button className="hud-factory-cancel" onClick={loadDiff} disabled={busy}>
        {showDiff ? "HIDE DIFF" : "VIEW DIFF"}
      </button>
      {showDiff && (
        <pre className="hud-dev-diff">{(detail && detail.diff) || "// loading…"}</pre>
      )}

      <div className="hud-factory-actions">
        <button className="hud-factory-approve" onClick={() => act("merge")} disabled={busy}>
          {busy ? "…" : "MERGE"}
        </button>
        <button className="hud-factory-cancel" onClick={() => act("escalate")} disabled={busy}>
          SEND TO CLAUDE
        </button>
        <button className="hud-factory-reject" onClick={() => act("reject")} disabled={busy}>
          REJECT
        </button>
      </div>
      <button className="hud-factory-cancel" onClick={() => _post(`/desktop/open-change/${change.id}`, () => {})}>
        OPEN IN EDITOR
      </button>
    </div>
  );
}

export function CodeReviewDock() {
  const { items, refresh } = usePolledQueue("/dev/pending");
  const [open, toggle] = useDockOpen("codereview");

  return (
    <div className="hud-dev-wrap">
      <div className="hud-factory-face" onClick={toggle}>
        <span className="hud-dev-tag">CODE REVIEW</span>
        <span className={`hud-factory-count ${items.length ? "hud-count-hot" : ""}`}>{items.length}</span>
      </div>
      {open && (
        <div className="hud-factory-panel">
          <div className="hud-factory-panel-header">◆ PROPOSED SELF-CHANGES</div>
          {items.length === 0
            ? <div className="hud-factory-empty">{"// no changes awaiting review"}</div>
            : items.map(c => <DevReviewCard key={c.id} change={c} onResolved={refresh} />)}
        </div>
      )}
    </div>
  );
}

// ── Builds dock: standalone apps RAMBO built — open, run, or test them ──
function BuildCard({ build: b }) {
  const [busy, setBusy] = useState("");
  const [out, setOut] = useState(null);

  const statusLabel =
    b.status === "building" ? "BUILDING…" : b.status === "failed" ? "FAILED" : "READY";

  const act = async (verb) => {
    if (busy) return;
    setBusy(verb); setOut(null);
    try {
      const r = await fetch(`${API}/builds/${b.slug}/${verb}`, { method: "POST" });
      setOut(await r.json());
    } catch { setOut({ error: "request failed" }); }
    finally { setBusy(""); }
  };

  const renderOut = (o) => {
    if (o.error) return `error: ${o.error}`;
    const head = o.timed_out ? "⏱ stopped (still running)"
      : o.ok ? "✓ ok" : "✗ failed";
    return `${head}${o.entry ? ` — ${o.entry}` : ""}\n\n${o.output || ""}`;
  };

  return (
    <div className="hud-factory-card">
      <div className="hud-factory-card-head">
        <span className="hud-factory-name">{b.name || b.slug}</span>
        <span className={`hud-dev-rec hud-dev-rec-${b.status === "ready" ? "merge" : b.status === "failed" ? "hold" : "escalate"}`}>
          {statusLabel}
        </span>
      </div>
      {b.summary && <div className="hud-factory-specialty">{b.summary}</div>}
      {b.host_path && <div className="hud-builds-path">{b.host_path}</div>}
      {b.files && b.files.length > 0 && (
        <div className="hud-factory-iter">{b.files.length} file{b.files.length === 1 ? "" : "s"}</div>
      )}
      {b.status === "ready" && (
        <div className="hud-factory-actions">
          {b.host_path && (
            <button className="hud-factory-approve" onClick={() => openOnDesktop(b.host_path)}>OPEN</button>
          )}
          <button className="hud-factory-cancel" onClick={() => act("test")} disabled={!!busy}>
            {busy === "test" ? "…" : "RUN TESTS"}
          </button>
          <button className="hud-factory-cancel" onClick={() => act("run")} disabled={!!busy}>
            {busy === "run" ? "…" : "RUN"}
          </button>
        </div>
      )}
      {out && <pre className="hud-dev-diff">{renderOut(out)}</pre>}
      {b.status === "failed" && b.error && (
        <div className="hud-factory-iter">error: {b.error}</div>
      )}
    </div>
  );
}

export function BuildsDock() {
  const { items } = usePolledQueue("/builds");
  const [open, toggle] = useDockOpen("builds");
  const ready = items.filter(b => b.status === "ready");

  return (
    <div className="hud-builds-wrap">
      <div className="hud-factory-face" onClick={toggle}>
        <span className="hud-builds-tag">BUILDS</span>
        <span className={`hud-factory-count ${ready.length ? "hud-count-hot" : ""}`}>{items.length}</span>
      </div>
      {open && (
        <div className="hud-factory-panel">
          <div className="hud-factory-panel-header">◆ BUILT PROJECTS</div>
          {items.length === 0
            ? <div className="hud-factory-empty">{"// nothing built yet"}</div>
            : items.map(b => <BuildCard key={b.id || b.slug} build={b} />)}
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

// Settings popover (gear button). Holds operator toggles — starting with Sound.
// Extend by adding more rows inside the panel.
export function SettingsPanel() {
  const [open, setOpen] = useState(false);
  const [soundOn, setSoundOn] = useState(!isMuted());
  const [vol, setVol] = useState(isMuted() ? 0 : getVolume());
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const toggleSound = () => {
    const next = !soundOn;
    // RAMBO's OWN audio only (voice + chimes) — Spotify has its own volume/mute
    // on the player widget. ON → 100%, OFF → 0%; the slider follows. setVolume
    // manages the mute flag (0 → muted, >0 → unmuted).
    const v = setVolume(next ? 100 : 0);
    setVol(v);
    setSoundOn(next);
    if (next) resumeAudio();
  };

  const onVol = (e) => {
    resumeAudio();
    const v = setVolume(parseInt(e.target.value, 10));  // RAMBO audio only (voice/chimes)
    setVol(v);
    setSoundOn(v > 0);
  };

  return (
    <div className="hud-settings" ref={ref}>
      <button className="hud-settings-btn" type="button" onClick={() => setOpen(o => !o)} title="Settings">⚙</button>
      {open && (
        <div className="hud-settings-panel">
          <div className="hud-cost-panel-header">◆ SETTINGS</div>
          <div className="hud-settings-row">
            <span>RAMBO Voice</span>
            <button className={`hud-toggle ${soundOn ? "hud-toggle-on" : "hud-toggle-off"}`}
              type="button" onClick={toggleSound}>
              {soundOn ? "ON" : "OFF"}
            </button>
          </div>
          <div className="hud-settings-row hud-vol-row">
            <span>Voice volume</span>
            <span className="hud-vol-val">{vol}%</span>
          </div>
          <input
            className="hud-vol-slider"
            type="range" min="0" max="100" step="5"
            value={vol}
            onChange={onVol}
            aria-label="Volume"
          />
          <div className="hud-vol-ticks">
            <span>0</span><span>25</span><span>50</span><span>75</span><span>100</span>
          </div>
        </div>
      )}
    </div>
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
  const [sharing, setSharing] = useState(isSharing());
  const locRef = useRef({ lat: null, lon: null });

  useEffect(() => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (pos) => { locRef.current = { lat: pos.coords.latitude, lon: pos.coords.longitude }; },
      () => {},
      { timeout: 8000, maximumAge: 600000 },
    );
  }, []);

  // Keep the toggle in sync with the screen-share state (incl. the browser's
  // own "Stop sharing" button, which fires the stream's ended event).
  useEffect(() => onShareChange(setSharing), []);

  // Auto-begin screen share on the operator's first interaction (browsers block
  // getDisplayMedia at page load). With the startup auto-select flag this is silent.
  useEffect(() => armAutoStart(), []);

  const toggleScreen = async () => {
    if (isSharing()) { stopShare(); return; }
    try { await startShare(); } catch { /* user cancelled the picker, or unsupported */ }
  };

  const submit = async (e) => {
    e.preventDefault();
    const g = goal.trim();
    if (!g || busy) return;
    setBusy(true);
    try {
      const image = frameForGoal(g);  // screen frame when sharing + screen-directed
      const body = { goal: g, lat: locRef.current.lat, lon: locRef.current.lon };
      if (image) body.image = image;
      await fetch(`${API}/rambo/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
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
        <button
          type="button"
          className={`hud-cmd-screen ${sharing ? "on" : ""}`}
          onClick={toggleScreen}
          title={sharing ? "R.A.M.B.O can see your screen — click to stop" : "Let R.A.M.B.O see your screen"}
        >
          {sharing ? "👁 SCREEN ON" : "👁 SCREEN"}
        </button>
        <button className="hud-cmd-exec" type="submit" disabled={busy || !goal.trim()}>
          {busy ? "RUNNING…" : "EXECUTE"}
        </button>
      </form>
    </div>
  );
}

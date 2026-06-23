import React, { useState, useEffect, useRef, useCallback } from "react";
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

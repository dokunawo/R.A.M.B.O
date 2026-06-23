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

import React, { useState, useEffect, useCallback } from "react";
import { useDockOpen } from "./SharedHUD";
import "./TodosPanel.css";

const API = "http://localhost:8000";
const POLL_MS = 8000;

function TaskRow({ t }) {
  const overdue = t.due_date && t.due_date < new Date().toISOString().slice(0, 10);
  return (
    <div className={`tp-row tp-prio-${t.priority}`}>
      <span className="tp-dot" />
      <span className="tp-text">{t.text}</span>
      {t.recurrence && <span className="tp-badge tp-badge-recur">↻</span>}
      {t.due_date && (
        <span className={`tp-badge ${overdue ? "tp-badge-overdue" : "tp-badge-due"}`}>
          {t.due_date}
        </span>
      )}
    </div>
  );
}

export default function TodosPanel() {
  const [items, setItems] = useState([]);
  const [open, toggle] = useDockOpen("todos");

  const refresh = useCallback(async () => {
    if (document.hidden) return;
    try {
      const r = await fetch(`${API}/todos`);
      if (r.ok) setItems(await r.json());
    } catch { /* offline — keep showing the last-known list */ }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_MS);
    const onVis = () => { if (!document.hidden) refresh(); };
    document.addEventListener("visibilitychange", onVis);
    return () => { clearInterval(id); document.removeEventListener("visibilitychange", onVis); };
  }, [refresh]);

  return (
    <div className="hud-builds-wrap">
      <div className="hud-factory-face" onClick={toggle}>
        <span className="hud-builds-tag">TO-DO</span>
        <span className={`hud-factory-count ${items.length ? "hud-count-hot" : ""}`}>
          {items.length}
        </span>
      </div>
      {open && (
        <div className="hud-factory-panel tp-panel">
          <div className="hud-factory-panel-header hud-dock-header">
            <span>◆ OPEN TASKS</span>
          </div>
          {items.length === 0
            ? <div className="hud-factory-empty">{"// nothing on your list"}</div>
            : items.map(t => <TaskRow key={t.id} t={t} />)}
        </div>
      )}
    </div>
  );
}

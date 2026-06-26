// Cmd/Ctrl+K command palette — quick actions, agent jumps, and run-a-command.
// Opens over any screen; Esc closes. Running a command POSTs to /rambo/execute
// (same path as voice/typed input); the WS pipeline shows the response.
import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";

const API = "http://localhost:8000";

// Static destinations + actions. "Run command" is synthesized from the query.
const NAV_ACTIONS = [
  { label: "Go to Command Center", to: "/" },
  { label: "Open Planner", to: "/agent/planner" },
  { label: "Open Executor", to: "/agent/executor" },
  { label: "Open Researcher", to: "/agent/researcher" },
  { label: "Open Keeper", to: "/agent/keeper" },
  { label: "Open Learning Log", to: "/learning" },
  { label: "Open Round Table", to: "/council" },
];

export default function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const inputRef = useRef(null);
  const nav = useNavigate();

  // Global Cmd/Ctrl+K toggle.
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(o => !o);
      } else if (e.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) { setQ(""); setSel(0); setTimeout(() => inputRef.current?.focus(), 30); }
  }, [open]);

  const runCommand = useCallback((text) => {
    fetch(`${API}/rambo/execute`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ goal: text }),
    }).catch(() => {});
  }, []);

  // Build the candidate list: matching nav actions + a "run command" row.
  const ql = q.trim().toLowerCase();
  const navMatches = NAV_ACTIONS.filter(a => !ql || a.label.toLowerCase().includes(ql));
  const items = [
    ...(q.trim() ? [{ label: `Run: “${q.trim()}”`, run: true }] : []),
    ...navMatches,
  ];

  const choose = (item) => {
    if (!item) return;
    setOpen(false);
    if (item.run) runCommand(q.trim());
    else if (item.to) nav(item.to);
  };

  const onKeyDown = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setSel(s => Math.min(s + 1, items.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setSel(s => Math.max(s - 1, 0)); }
    else if (e.key === "Enter") { e.preventDefault(); choose(items[sel]); }
  };

  if (!open) return null;

  return (
    <div className="hud-cmdk-overlay" onClick={() => setOpen(false)}>
      <div className="hud-cmdk-panel" onClick={e => e.stopPropagation()}>
        <input
          ref={inputRef}
          className="hud-cmdk-input"
          value={q}
          placeholder="Type a command or jump to…  (Esc to close)"
          spellCheck={false}
          onChange={e => { setQ(e.target.value); setSel(0); }}
          onKeyDown={onKeyDown}
        />
        <div className="hud-cmdk-list">
          {items.length === 0
            ? <div className="hud-cmdk-empty">{"// no matches"}</div>
            : items.map((it, i) => (
                <div
                  key={i}
                  className={`hud-cmdk-item ${i === sel ? "hud-cmdk-sel" : ""}`}
                  onMouseEnter={() => setSel(i)}
                  onClick={() => choose(it)}
                >
                  {it.run ? "▶ " : "→ "}{it.label}
                </div>
              ))}
        </div>
      </div>
    </div>
  );
}

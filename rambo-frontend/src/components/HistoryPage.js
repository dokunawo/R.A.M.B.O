import React, { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Canvas } from "@react-three/fiber";
import { EffectComposer, Bloom } from "@react-three/postprocessing";
import CosmicOrb from "./CosmicOrb";
import CosmicBackground from "./CosmicBackground";
import { usePageVoice, VoiceControls } from "./VoiceControls";
import { useSystemStats, StatBars, SoundGate, SettingsPanel } from "./SharedHUD";
import CommandPalette from "./CommandPalette";
import "./LearningLog.css";
import "./AgentPage.css";
import "./HistoryPage.css";

const API = "http://localhost:8000";

function fmtTime(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString([], { month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit" });
  } catch { return ""; }
}

function HistoryPage() {
  const navigate = useNavigate();
  const { micActive, toggleMic, state: convState, levelRef: audioLevelRef } =
    usePageVoice({ onCommandCenter: () => navigate("/console") });
  const sysStats = useSystemStats();
  const [entries, setEntries] = useState([]);
  const [copied, setCopied] = useState(null);   // id of last-copied entry (for feedback)

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

  const fetchEntries = useCallback(async () => {
    try {
      const r = await fetch(`${API}/transcript?limit=200`);
      if (r.ok) { const j = await r.json(); setEntries(j.entries || []); }
    } catch {}
  }, []);

  useEffect(() => {
    fetchEntries();
    const id = setInterval(fetchEntries, 5000);
    return () => clearInterval(id);
  }, [fetchEntries]);

  const copy = (text, id) => {
    try {
      navigator.clipboard.writeText(text);
      setCopied(id);
      setTimeout(() => setCopied(c => (c === id ? null : c)), 1500);
    } catch {}
  };
  const copyEntry = (e) => copy(`Q: ${e.question}\n\nA: ${e.answer}`, e.id);
  const copyAll = () => copy(
    entries.map(e => `Q: ${e.question}\n\nA: ${e.answer}`).join("\n\n———\n\n"), "all");

  const clearAll = async () => {
    try { await fetch(`${API}/transcript`, { method: "DELETE" }); setEntries([]); } catch {}
  };

  // newest first for reading
  const ordered = [...entries].reverse();

  return (
    <div className="ll-root">
      <div className="ll-orb-bg">
        <Canvas camera={{ position: [0, 0, 4.2], fov: 45 }}
          dpr={[1, 1.5]} gl={{ antialias: true, alpha: true, premultipliedAlpha: false, powerPreference: 'high-performance', stencil: false }}>
          <CosmicBackground />
          <CosmicOrb mouseRef={mouseRef} audioLevelRef={audioLevelRef} />
          <EffectComposer>
            <Bloom luminanceThreshold={0.7} luminanceSmoothing={0.95} intensity={0.6} radius={0.5} />
          </EffectComposer>
        </Canvas>
      </div>
      <div className="ll-grid-overlay" />

      <header className="ll-topbar">
        <button className="ll-back-btn" onClick={() => navigate("/console")}>
          ← COMMAND CENTER
        </button>
        <div className="ll-topbar-title">HISTORY</div>
        <div className="ll-topbar-right">
          <span className="hist-entry-count">{entries.length} saved</span>
        </div>
      </header>

      <div className="hist-wrap">
        <div className="hist-toolbar">
          <span className="hist-toolbar-title">◆ QUESTIONS &amp; ANSWERS</span>
          <span className="hist-toolbar-actions">
            <button className="hist-btn" onClick={copyAll} disabled={!entries.length}>
              {copied === "all" ? "✓ copied" : "Copy all"}
            </button>
            <button className="hist-btn hist-btn-danger" onClick={clearAll} disabled={!entries.length}>
              Clear history
            </button>
          </span>
        </div>

        {ordered.length === 0 ? (
          <div className="hist-empty">{"// nothing saved yet — ask R.A.M.B.O something"}</div>
        ) : (
          <div className="hist-list">
            {ordered.map((e) => (
              <div key={e.id} className="hist-item">
                <div className="hist-item-head">
                  <span className="hist-time">{fmtTime(e.created_at)}</span>
                  <button className="hist-copy" onClick={() => copyEntry(e)}>
                    {copied === e.id ? "✓ copied" : "Copy"}
                  </button>
                </div>
                <div className="hist-q">&gt; {e.question}</div>
                <div className="hist-a">{e.answer}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      <StatBars stats={sysStats} />
      <SoundGate />
      <SettingsPanel />
      <CommandPalette />
      <VoiceControls micActive={micActive} toggleMic={toggleMic} convState={convState} />
    </div>
  );
}

export default HistoryPage;

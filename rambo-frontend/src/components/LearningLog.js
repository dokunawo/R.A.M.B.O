import React, { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Canvas } from "@react-three/fiber";
import { EffectComposer, Bloom, ChromaticAberration } from "@react-three/postprocessing";
import { Vector2 } from "three";
import CosmicOrb from "./CosmicOrb";
import CosmicBackground from "./CosmicBackground";
import { usePageVoice, VoiceControls, CommandLog } from "./VoiceControls";
import "./LearningLog.css";

const API = "http://localhost:8000";

function LiveClock() {
  const [time, setTime] = useState(new Date());
  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  const date = time.toLocaleDateString("en-US", { month: "2-digit", day: "2-digit", year: "numeric" });
  const clock = time.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  return <span className="ll-clock">{date} — {clock}</span>;
}

function LearningLog() {
  const navigate = useNavigate();
  const { micActive, toggleMic, state: convState, levelRef: audioLevelRef, commandLog } = usePageVoice();
  const [learnings, setLearnings] = useState([]);

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

  const fetchLearnings = useCallback(async () => {
    try {
      const r = await fetch(`${API}/learning/log`);
      if (r.ok) setLearnings(await r.json());
    } catch {}
  }, []);

  useEffect(() => {
    fetchLearnings();
    const id = setInterval(fetchLearnings, 5000);
    return () => clearInterval(id);
  }, [fetchLearnings]);

  return (
    <div className="ll-root">
      {/* full-screen orb background — same as Phase 2 */}
      <div className="ll-orb-bg">
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
      </div>

      <div className="ll-grid-overlay" />

      <header className="ll-topbar">
        <button className="ll-back-btn" onClick={() => navigate("/console")}>
          ← COMMAND CENTER
        </button>
        <div className="ll-topbar-title">LEARNING LOG</div>
        <div className="ll-topbar-right">
          <span className="ll-council-link" onClick={() => navigate("/council")}>
            ◆ COUNCIL VIEW
          </span>
          <LiveClock />
        </div>
      </header>

      {/* content centered over the orb */}
      <div className="ll-center-content">
        <section className="ll-info-card">
          <div className="ll-info-icon">🧬</div>
          <div className="ll-info-text">
            <h2 className="ll-title">R.A.M.B.O LEARNING LOG</h2>
            <p className="ll-subtitle">
              A running record of patterns, corrections, and adaptations across
              all operational cycles.
            </p>
          </div>
        </section>

        <section className="ll-section">
          <h3 className="ll-section-title">◆ RECENT LEARNINGS</h3>
          {learnings.length === 0 ? (
            <div className="ll-empty">
              <p>No learnings recorded yet.</p>
              <p className="ll-empty-sub">
                Learnings are captured automatically as R.A.M.B.O processes tasks
                and receives operator feedback.
              </p>
            </div>
          ) : (
            <ul className="ll-list">
              {learnings.map((l, i) => (
                <li key={i} className="ll-item">
                  <div className="ll-item-head">
                    <span className="ll-item-source">{l.source || "System"}</span>
                    <span className="ll-item-time">{l.time || "—"}</span>
                  </div>
                  <p className="ll-item-text">{l.text}</p>
                  {l.category && (
                    <span className="ll-item-cat">{l.category}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="ll-section">
          <h3 className="ll-section-title">◆ OPERATIONAL LEARNING</h3>
          <p className="ll-op-desc">
            R.A.M.B.O continuously adapts through operator corrections,
            task outcomes, and pattern recognition across all agent interactions.
          </p>
        </section>
      </div>

      <footer className="ll-footer">
        <span>R.A.M.B.O — Accuracy · Precision · Execution</span>
        <span>© {new Date().getFullYear()}</span>
      </footer>

      <CommandLog commandLog={commandLog} agentColor="#ff4466" />
      <VoiceControls micActive={micActive} toggleMic={toggleMic} convState={convState} />
    </div>
  );
}

export default LearningLog;

import React, { useEffect, useRef, useState } from "react";
import "./ShutdownSequence.css";

const API = "http://localhost:8000";

/**
 * Cinematic shutdown/logout sequence — purely a UX sign-off. It speaks the
 * backend farewell, plays an orb power-down, then drops to a STANDBY lock. No
 * process is stopped; "WAKE" returns to the live console.
 *
 * Props:
 *   speak(text, followUp)  — ElevenLabs speak fn (SplashScreen's speakRef.current)
 *   onWake()               — dismiss the overlay, back to the console
 */
export default function ShutdownSequence({ speak, onWake }) {
  const [stage, setStage] = useState("powering");   // "powering" → "standby"
  const startedRef = useRef(false);

  useEffect(() => {
    if (startedRef.current) return;     // fire the farewell once, not on re-render
    startedRef.current = true;
    let alive = true;

    (async () => {
      let line = "Powering down to standby.";
      try {
        const r = await fetch(`${API}/farewell`);
        if (r.ok) {
          const j = await r.json();
          if (j && j.farewell) line = j.farewell;
        }
      } catch { /* speak the fallback line */ }
      if (!alive) return;
      try { if (speak) speak(line, false); } catch { /* audio may be locked */ }
    })();

    const t = setTimeout(() => { if (alive) setStage("standby"); }, 4200);
    return () => { alive = false; clearTimeout(t); };
  }, [speak]);

  return (
    <div className={`ss-overlay ss-${stage}`} role="dialog" aria-label="System standby">
      <div className="ss-orb-collapse" />
      {stage === "powering" ? (
        <div className="ss-panel">
          <div className="ss-title">R.A.M.B.O</div>
          <div className="ss-sub">Powering down to standby…</div>
        </div>
      ) : (
        <div className="ss-panel">
          <div className="ss-mark">⏻</div>
          <div className="ss-title">STANDBY</div>
          <div className="ss-sub">Systems idle — R.A.M.B.O is listening for you.</div>
          <button className="ss-wake" onClick={onWake}>WAKE</button>
        </div>
      )}
    </div>
  );
}

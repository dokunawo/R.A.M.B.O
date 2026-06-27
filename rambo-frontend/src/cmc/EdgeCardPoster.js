import React, { useState, useEffect, useRef, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import "./poster.css";

const API = "http://localhost:8000";

const TITLES = {
  hr: "HOME RUNS", hrr: "HITS + RUNS + RBI", sb: "STOLEN BASES",
  k: "STRIKEOUTS", ml: "MONEYLINE",
};
const GLOW = { gold: "#d6a21e", green: "#39ff5a", blue: "#4ea0ff", red: "#ff5a5a" };
const todayISO = () => new Date().toISOString().slice(0, 10);
const pct = (x) => `${x >= 0 ? "+" : "−"}${Math.abs(x * 100).toFixed(1)}%`;
const prettyDate = (iso) => {
  try { return new Date(iso + "T12:00:00").toLocaleDateString("en-US", { month: "long", day: "numeric" }).toUpperCase(); }
  catch { return iso; }
};

function Crown() {
  return (
    <svg className="poster-crown" width="120" height="74" viewBox="0 0 120 74" fill="none" aria-hidden="true">
      <path d="M10 64 L6 20 L34 42 L60 8 L86 42 L114 20 L110 64 Z"
            fill="#d6a21e" stroke="#f0cf73" strokeWidth="2" strokeLinejoin="round" />
      <circle cx="6" cy="16" r="5" fill="#f0cf73" />
      <circle cx="60" cy="6" r="6" fill="#f0cf73" />
      <circle cx="114" cy="16" r="5" fill="#f0cf73" />
      <rect x="8" y="62" width="104" height="7" rx="2" fill="#b9851a" />
    </svg>
  );
}

function Tile({ pick }) {
  const isML = pick.market === "ml";
  const pos = pick.edge > 0;
  const hot = !isML && pos && pick.model_p > 0.65;
  return (
    <div className="ptile">
      <span className="br tl" /><span className="br tr" /><span className="br bl" /><span className="br brr" />
      <div className="ptile-top">
        <div className="porb" style={{ "--g": GLOW[pick.glow] || GLOW.gold }}><span>{pick.initials}</span></div>
        <div className="ptile-id">
          <div className="ptile-name">{pick.name}</div>
          <div className="ptile-matchup">
            {pick.team} // vs {pick.opponent}{pick.hand ? ` // ${pick.hand}` : ""}
          </div>
        </div>
      </div>
      <div className="ptile-pick">{pick.pick}</div>
      <div className="ptile-stats">
        <div className="ptile-mb">
          MODEL <b className="m">{Math.round(pick.model_p * 100)}%</b><br />
          {isML ? "MKT" : "B/E"} <b className="k">{Math.round(pick.breakeven * 100)}%</b>
          {!isML && pick.multiplier ? <span> · {pick.multiplier}×</span> : null}
        </div>
        <div className={`ptile-edge ${pos ? "pos" : "neg"}`}>{pct(pick.edge)}</div>
      </div>
      <div className="ptile-tags">
        {isML ? <span className="ptag lean">LEAN</span>
          : pos ? <span className="ptag edge">EDGE</span>
                : <span className="ptag skip">−EV · SKIP</span>}
        {hot ? <span className="ptag hot">HOT</span> : null}
      </div>
    </div>
  );
}

export default function EdgeCardPoster() {
  const { market = "hr" } = useParams();
  const date = todayISO();
  const [picks, setPicks] = useState(null);
  const [busy, setBusy] = useState(false);
  const posterRef = useRef(null);

  useEffect(() => {
    let live = true;
    fetch(`${API}/betting/daily-edge?market=${market}&date=${date}&threshold=-1`)
      .then((r) => r.ok ? r.json() : Promise.reject(r.status))
      .then((j) => { if (live) setPicks((j.picks || []).slice(0, 4)); })
      .catch(() => { if (live) setPicks([]); });
    return () => { live = false; };
  }, [market, date]);

  const download = useCallback(async () => {
    if (!posterRef.current) return;
    setBusy(true);
    try {
      await document.fonts.ready;
      const { toPng } = await import("html-to-image");
      const url = await toPng(posterRef.current, { pixelRatio: 2, cacheBust: true, backgroundColor: "#050504" });
      const a = document.createElement("a");
      a.download = `CMC-${market}-${date}.png`;
      a.href = url;
      a.click();
    } catch (e) {
      alert("Export failed: " + (e && e.message));
    } finally {
      setBusy(false);
    }
  }, [market, date]);

  const anyPos = (picks || []).some((p) => p.edge > 0);
  const title = TITLES[market] || market.toUpperCase();

  return (
    <div className="poster-page">
      <div className="poster-actions">
        <button className="poster-btn" onClick={download} disabled={busy}>
          {busy ? "Rendering…" : "⬇ Download PNG"}
        </button>
        {["hr", "hrr", "sb", "k", "ml"].map((m) => (
          <Link key={m} className="poster-btn ghost" to={`/card/${m}`}>{m.toUpperCase()}</Link>
        ))}
      </div>
      <div className="poster-hint">High-res card · powered by R.A.M.B.O · {prettyDate(date)}</div>

      <div className="poster" ref={posterRef}>
        <Crown />
        <div className="poster-wordmark">
          <span className="pw-1">CHANCES</span>
          <span className="pw-2">MAKE</span>
          <span className="pw-3">CHAMPIONS</span>
        </div>

        <div className="poster-panel">
          <div className="panel-head">
            <div className="panel-title">{title}</div>
            <div className="panel-right">
              <div className="panel-date">{prettyDate(date)}</div>
              <div className="panel-org">R.A.M.B.O</div>
            </div>
          </div>
          <div className="panel-sub">
            {anyPos ? "TOP +EV PLAYS // MLB" : "−EV TODAY · MODEL SAYS SKIP // MLB"}
          </div>

          {picks === null && <div className="poster-empty">Reading the slate…</div>}
          {picks && picks.length === 0 && <div className="poster-empty">No lines for this market today.</div>}
          {picks && picks.length > 0 && (
            <div className="panel-grid">
              {picks.map((p, i) => <Tile key={`${p.mlb_id}-${i}`} pick={p} />)}
            </div>
          )}

          <div className="panel-foot">
            <div className="l">{(picks || []).length} LEGS // MODEL VS MARKET // RANK-ONLY</div>
            <div className="r">{anyPos ? "PLAY ON" : "SKIP"}</div>
          </div>
        </div>

        <div className="poster-foot"><span className="cmc">♛ CMC</span></div>
      </div>
    </div>
  );
}

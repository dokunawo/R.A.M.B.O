import React, { useState, useEffect, useRef, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import "./poster.css";

const API = "http://localhost:8000";

const TITLES = { hr: "HOME RUNS", hrr: "HITS + RUNS + RBI", sb: "STOLEN BASES", k: "STRIKEOUTS", ml: "MONEYLINE" };
const CAPS = { hr: "DK Pick6 · 1+ HR", hrr: "DK Pick6 · H+R+RBI", sb: "DK Pick6 · Stolen Bases", k: "DK Pick6 · Strikeouts", ml: "Model vs Market" };
const NOUN = { hr: "home runs", hrr: "H+R+RBI", sb: "stolen bases", k: "strikeouts", ml: "moneyline" };
const GLOW = { gold: "#d6a21e", green: "#39ff5a", blue: "#4ea0ff", red: "#ff5a5a" };
const todayISO = () => new Date().toISOString().slice(0, 10);
const pct = (x) => `${x >= 0 ? "+" : "−"}${Math.abs(x * 100).toFixed(1)}%`;
const prettyDate = (iso) => {
  try { return new Date(iso + "T12:00:00").toLocaleDateString("en-US", { month: "long", day: "numeric" }).toUpperCase(); }
  catch { return iso; }
};

// Uses the operator's ChatGPT logo (public/cmc/cmc-logo.png) when present; falls
// back to the CSS gold-foil wordmark until that file is dropped in.
function CmcMark() {
  const [png, setPng] = useState(true);
  if (png) {
    return <img className="cmc-logo-img" crossOrigin="anonymous" src="/cmc/cmc-logo.png"
                alt="Chances Make Champions" onError={() => setPng(false)} />;
  }
  return (
    <>
      <Crown w={50} />
      <div className="mark gold-foil">CMC</div>
      <div className="full">CHANCES MAKE <b>CHAMPIONS</b></div>
    </>
  );
}

function BrushUnderline() {
  return (
    <svg className="brush" width="420" height="26" viewBox="0 0 420 26" fill="none" aria-hidden="true">
      <path d="M8 15 C90 4 170 18 250 11 C320 5 372 8 412 14 C372 22 300 25 210 20 C140 16 70 24 8 15 Z"
            fill="#d6a21e" />
      <path d="M30 17 C120 10 220 19 300 13" stroke="#f0cf73" strokeWidth="2" strokeLinecap="round" opacity="0.6" fill="none" />
    </svg>
  );
}

function Crown({ w = 56 }) {
  return (
    <svg className="crown" width={w} height={w * 0.62} viewBox="0 0 120 74" fill="none" aria-hidden="true">
      <path d="M10 64 L6 20 L34 42 L60 8 L86 42 L114 20 L110 64 Z" fill="#d6a21e" stroke="#f0cf73" strokeWidth="2" strokeLinejoin="round" />
      <circle cx="6" cy="16" r="5" fill="#f0cf73" /><circle cx="60" cy="6" r="6" fill="#f0cf73" /><circle cx="114" cy="16" r="5" fill="#f0cf73" />
      <rect x="8" y="62" width="104" height="7" rx="2" fill="#b9851a" />
    </svg>
  );
}

function Orb({ pick }) {
  const [bad, setBad] = useState(false);
  const logo = (pick.headshot_url || "").includes("team-logos");
  return (
    <div className="porb" style={{ "--g": GLOW[pick.glow] || GLOW.gold }}>
      {pick.headshot_url && !bad
        ? <img crossOrigin="anonymous" src={pick.headshot_url} alt=""
               style={logo ? { objectFit: "contain", padding: "12px" } : undefined}
               onError={() => setBad(true)} />
        : <span>{pick.initials}</span>}
    </div>
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
        <Orb pick={pick} />
        <div className="ptile-id">
          <div className="ptile-name">{pick.name}</div>
          <div className="ptile-matchup">vs {pick.opponent}{pick.hand ? ` · ${pick.hand}HP` : ""}</div>
        </div>
      </div>
      <div className="ptile-pick">{pick.pick}</div>
      <div className="ptile-stats">
        <div className={`ptile-edge ${pos ? "pos" : "neg"}`}>
          <span className="num">{pct(pick.edge)}</span>
          <span className="cap">MODEL EDGE</span>
        </div>
        <div className="ptile-mb">
          MODEL <b className="m">{Math.round(pick.model_p * 100)}%</b><br />
          {isML ? "MKT" : "B/E"} <b>{Math.round(pick.breakeven * 100)}%</b>
          {!isML && pick.multiplier ? <><br />MULT <b className="x">{pick.multiplier}×</b></> : null}
        </div>
      </div>
      {pick.support ? <div className="ptile-season">{pick.support}</div> : null}
      <div>
        {isML ? <span className="ptile-tag lean">LEAN</span>
          : pos ? <span className="ptile-tag edge">EDGE</span>
                : <span className="ptile-tag skip">−EV · SKIP</span>}
        {hot ? <span className="ptile-tag hot">HOT</span> : null}
      </div>
    </div>
  );
}

function Banner({ market, anyPos }) {
  if (market === "ml") {
    return (
      <div className="poster-banner" style={{ "--bc": "rgba(214,162,30,.45)", "--bg": "rgba(214,162,30,.06)", "--hl": "#e7cd86" }}>
        <span className="icon">⚖️</span>
        <span className="txt"><b>Leans, not locks.</b> Each pick is the model's small disagreement with the de-vigged market — strongest first. Not bet signals; bet your own number.</span>
      </div>
    );
  }
  if (anyPos) {
    return (
      <div className="poster-banner" style={{ "--bc": "rgba(57,255,90,.4)", "--bg": "rgba(57,255,90,.05)", "--hl": "#39ff5a" }}>
        <span className="icon">✅</span>
        <span className="txt"><b>+EV today.</b> The model beats the {NOUN[market]} line on these legs. Ranked by edge.</span>
      </div>
    );
  }
  return (
    <div className="poster-banner">
      <span className="icon">🚫</span>
      <span className="txt">
        <b>−EV today — no play.</b> Every DK Pick6 {NOUN[market]} leg is priced against you
        (the multiplier carries the house margin). The model is steering you away. Closest legs below for transparency:
      </span>
    </div>
  );
}

export default function EdgeCardPoster() {
  const { market = "hr" } = useParams();
  const date = todayISO();
  const [picks, setPicks] = useState(null);
  const [busy, setBusy] = useState(false);
  const [plate, setPlate] = useState(false);   // true once public/cmc/plate.png exists
  const posterRef = useRef(null);

  useEffect(() => {
    let live = true;
    fetch(`${API}/betting/daily-edge?market=${market}&date=${date}&threshold=-1`)
      .then((r) => r.ok ? r.json() : Promise.reject(r.status))
      .then((j) => { if (live) setPicks((j.picks || []).slice(0, 3)); })
      .catch(() => { if (live) setPicks([]); });
    return () => { live = false; };
  }, [market, date]);

  // If the operator drops a ChatGPT-made branded plate at public/cmc/plate.png,
  // use it as the full background (logo + smoke baked in) and hide the CSS logo.
  useEffect(() => {
    const im = new Image();
    im.onload = () => setPlate(true);
    im.onerror = () => setPlate(false);
    im.src = `${process.env.PUBLIC_URL}/cmc/plate.png`;
  }, []);

  const download = useCallback(async () => {
    if (!posterRef.current) return;
    setBusy(true);
    try {
      await document.fonts.ready;
      const { toPng } = await import("html-to-image");
      const url = await toPng(posterRef.current, { pixelRatio: 2, cacheBust: true, backgroundColor: "#050504" });
      const a = document.createElement("a");
      a.download = `CMC-${market}-${date}.png`;
      a.href = url; a.click();
    } catch (e) {
      alert("Export failed: " + (e && e.message));
    } finally { setBusy(false); }
  }, [market, date]);

  const anyPos = (picks || []).some((p) => p.edge > 0);
  const title = TITLES[market] || market.toUpperCase();
  const footL = market === "ml" ? "MONEYLINE" : (CAPS[market] || "").toUpperCase();

  // public/cmc/* are same-origin assets; reference via PUBLIC_URL so css-loader
  // doesn't try to resolve them at build (and so the PNG export stays clean).
  const tex = `${process.env.PUBLIC_URL}/cmc`;
  const posterBg = plate
    ? { backgroundImage: `url(${tex}/plate.png)`, backgroundSize: "100% auto",
        backgroundPosition: "top center", backgroundRepeat: "no-repeat", backgroundColor: "#000" }
    : { backgroundImage: `url(${tex}/grunge.png), url(${tex}/gold-dust.png), url(${tex}/smoke-bg.png)`,
        backgroundSize: "cover", backgroundPosition: "center", backgroundRepeat: "no-repeat",
        backgroundColor: "#000" };

  return (
    <div className="poster-page">
      <div className="poster-actions">
        <button className="poster-btn" onClick={download} disabled={busy}>{busy ? "Rendering…" : "⬇ Download PNG"}</button>
        {["hr", "hrr", "sb", "k", "ml"].map((m) => (
          <Link key={m} className="poster-btn ghost" to={`/card/${m}`}>{m.toUpperCase()}</Link>
        ))}
      </div>
      <div className="poster-hint">High-res landscape card · live data · {prettyDate(date)}</div>

      <div className={`poster ${plate ? "has-plate" : ""}`} ref={posterRef} style={posterBg}>
        {!plate && <div className="cmc-logo"><CmcMark /></div>}

        <div className="hero">
          <h1 className="hr-title gold-foil">{title}</h1>
          <BrushUnderline />
          <div className="hero-cap">{CAPS[market] || ""}</div>
        </div>

        {picks && <Banner market={market} anyPos={anyPos} />}

        {picks === null && <div className="poster-empty">Reading the slate…</div>}
        {picks && picks.length === 0 && <div className="poster-empty">No lines for this market today.</div>}
        {picks && picks.length > 0 && (
          <div className="tiles">{picks.map((p, i) => <Tile key={`${p.mlb_id}-${i}`} pick={p} />)}</div>
        )}

        <div className="poster-foot">
          <div className="l">{footL} &nbsp;|&nbsp; MODEL POWERED BY <b>CMC</b></div>
          <div className="r">Always bet with an edge.</div>
        </div>
      </div>
    </div>
  );
}

import React, { useState, useEffect, useCallback } from "react";
import PickCard from "./PickCard";
import "./cmc.css";

const API = "http://localhost:8000";

// Moneyline leads (where real leans live); the four DK Pick6 prop markets follow,
// shown honestly as −EV "skip" states because single Pick6 legs are priced against
// the bettor. threshold=-1 pulls candidates too, so props aren't just blank cards.
const MARKETS = [
  { key: "ml",  title: "Moneyline Leans",      kind: "ml",   note: "model vs market — leans, NOT bet signals" },
  { key: "hr",  title: "Home Runs",            kind: "prop", note: "DK Pick6 · 1+ HR" },
  { key: "hrr", title: "Hits + Runs + RBIs",   kind: "prop", note: "DK Pick6" },
  { key: "sb",  title: "Stolen Bases",         kind: "prop", note: "DK Pick6" },
  { key: "k",   title: "Pitcher Strikeouts",   kind: "prop", note: "DK Pick6" },
];

const todayISO = () => new Date().toISOString().slice(0, 10);

function prettyDate(iso) {
  try {
    return new Date(iso + "T12:00:00").toLocaleDateString("en-US",
      { month: "long", day: "numeric", year: "numeric" }).toUpperCase();
  } catch { return iso; }
}

export default function ChancesMakeChampions({ date = todayISO() }) {
  const [data, setData] = useState(null);   // { [key]: picks[] }
  const [status, setStatus] = useState("loading");  // loading | ok | error

  const load = useCallback(async () => {
    setStatus("loading");
    try {
      const results = await Promise.all(MARKETS.map(async (m) => {
        const r = await fetch(`${API}/betting/daily-edge?market=${m.key}&date=${date}&threshold=-1`);
        if (!r.ok) throw new Error(`${m.key} ${r.status}`);
        const j = await r.json();
        return [m.key, j.picks || []];
      }));
      setData(Object.fromEntries(results));
      setStatus("ok");
    } catch {
      setStatus("error");
    }
  }, [date]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="cmc-root">
      <header className="cmc-header">
        <div className="cmc-crown">👑</div>
        <div className="cmc-wordmark">Chances Make Champions</div>
        <div className="cmc-sub">Daily Edge · {prettyDate(date)}</div>
        <div className="cmc-tagline">
          <b>+EV where it's real.</b> −EV called out, not dressed up. No fairy tales.
        </div>
      </header>

      {status === "loading" && (
        <div className="cmc-state"><div className="spin">👑</div><div>Reading the slate…</div></div>
      )}
      {status === "error" && (
        <div className="cmc-state">
          Engine offline. Start the RAMBO backend (:8000) and refresh.
        </div>
      )}

      {status === "ok" && MARKETS.map((m) => (
        <Section key={m.key} meta={m} picks={data[m.key] || []} />
      ))}

      <footer className="cmc-footer">
        <div className="cmc-foot-brand">👑 CMC</div>
        <div className="cmc-foot-note">Ranked by edge · model-vs-market · not financial advice</div>
      </footer>
    </div>
  );
}

function Section({ meta, picks }) {
  const isML = meta.kind === "ml";
  const positive = picks.filter((p) => p.edge > 0);
  const sorted = [...picks].sort((a, b) => b.edge - a.edge);

  // ml: show the leans (all are ≥0). props: show genuine +EV if any, else the
  // closest near-misses as honest -EV "skip" tiles.
  let tiles, emptyBanner = null;
  if (isML) {
    tiles = sorted;
  } else if (positive.length) {
    tiles = positive.sort((a, b) => b.edge - a.edge);
  } else {
    tiles = sorted.slice(0, 3);   // closest-to-break-even -EV candidates
    emptyBanner = (
      <div className="cmc-empty">
        <span className="x">🚫</span>
        <span className="txt">
          <b>−EV today — no play.</b> Every DK Pick6 {meta.title.toLowerCase()} leg is
          priced against you (the multiplier carries the house margin). The model is
          steering you away. Closest legs below for transparency:
        </span>
      </div>
    );
  }

  return (
    <section className="cmc-section">
      <div className="cmc-sec-head">
        <div className="cmc-sec-title">{meta.title}</div>
        <div className="cmc-sec-note">{meta.note}</div>
      </div>
      <div className="cmc-sec-rule" />
      <div className="cmc-grid">
        {emptyBanner}
        {tiles.length === 0 && !emptyBanner && (
          <div className="cmc-empty"><span className="x">∅</span>
            <span className="txt">No lines available for this market today.</span></div>
        )}
        {tiles.map((p, i) => (
          <PickCard key={`${p.mlb_id}-${p.pick}-${i}`} pick={p} kind={meta.kind}
                    rank={isML ? i : undefined} king={isML && i === 0} />
        ))}
      </div>
    </section>
  );
}

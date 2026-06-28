import React, { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import "./cmc.css";
import "./parlay.css";

const API = "http://localhost:8000";
const todayISO = () => new Date().toISOString().slice(0, 10);

function prettyDate(iso) {
  try {
    return new Date(iso + "T12:00:00").toLocaleDateString("en-US",
      { weekday: "short", month: "long", day: "numeric", year: "numeric" }).toUpperCase();
  } catch { return iso; }
}

// Each board: endpoint + how to render one row. Returns a {lead, cells} per row —
// `lead` is the big highlighted probability; `cells` are supporting columns.
const BOARDS = [
  {
    key: "player-watch", title: "PLAYER WATCH", sub: "Home runs",
    head: ["", "Hitter", "Matchup", "HR%", "Env / Form"],
    row: (r) => [
      r.is_lean ? "★" : "",
      r.name,
      `${r.team}${r.bats ? ` · ${r.bats}` : ""}${r.pitcher ? ` · vs ${r.pitcher}` : ""}`,
      `${r.hr_pct}%`,
      [r.venue && `${r.venue}${r.temp != null ? ` ${r.temp}°` : ""}`,
       `env ${r.env_pct >= 0 ? "+" : ""}${r.env_pct}%`, r.form].filter(Boolean).join("  ·  "),
    ],
    lead: 3,
  },
  {
    key: "strikeout-watch", title: "STRIKEOUT WATCH", sub: "Pitcher strikeouts",
    head: ["", "Pitcher", "Matchup", "9+ K", "8+ / 10+ · proj"],
    row: (r) => ["", r.name, `${r.team} vs ${r.opponent}`, `${r.p9}%`,
                 `8+ ${r.p8}%  ·  10+ ${r.p10}%  ·  ~${r.k_mean} K`],
    lead: 3,
  },
  {
    key: "hits-tb-watch", title: "HITS & TOTAL BASES", sub: "Hits / total bases",
    head: ["", "Hitter", "Matchup", "2+ TB", "1+ hit · proj"],
    row: (r) => ["", r.name, `${r.team} vs ${r.opponent}`, `${r.p_tb2}%`,
                 `1+ hit ${r.p_hit}%  ·  ${r.hit_mean}H / ${r.tb_mean}TB`],
    lead: 3,
  },
  {
    key: "moneyline-board", title: "MONEYLINE BOARD", sub: "Every game · our lean",
    head: ["", "Matchup", "Book", "Model", "Lean"],
    row: (r) => ["", `${r.away} @ ${r.home}`,
                 `${r.away} ${r.away_price >= 0 ? "+" : ""}${r.away_price} / ${r.home} ${r.home_price >= 0 ? "+" : ""}${r.home_price}`,
                 `${r.home} ${r.model_home_pct}% / ${r.away} ${r.model_away_pct}%`,
                 r.lean_side ? `${r.lean_side} +${r.lean_pct}%` : "no lean"],
    lead: 3,
  },
];

export default function ParlayBoards({ date = todayISO() }) {
  const [boards, setBoards] = useState({});
  const [status, setStatus] = useState("loading");

  const load = useCallback(async () => {
    setStatus("loading");
    try {
      const results = await Promise.all(BOARDS.map(async (b) => {
        const r = await fetch(`${API}/betting/${b.key}?date=${date}`);
        const j = r.ok ? await r.json() : { rows: [] };
        return [b.key, j.rows || []];
      }));
      setBoards(Object.fromEntries(results));
      setStatus("ok");
    } catch { setStatus("error"); }
  }, [date]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="cmc-root pb-root">
      <header className="pb-head">
        <div>
          <h1 className="pb-title">PARLAY BOARDS</h1>
          <div className="pb-date">{prettyDate(date)} · Chances Make Champions</div>
        </div>
        <div className="pb-nav">
          <button className="pb-btn" onClick={load}>↻ Refresh</button>
          <Link className="pb-btn" to="/edge">Daily Edge</Link>
          <Link className="pb-btn" to="/">Console</Link>
        </div>
      </header>

      {status === "error" && <div className="pb-empty">Backend unreachable — is it up on :8000?</div>}

      <div className="pb-grid">
        {BOARDS.map((b) => {
          const rows = boards[b.key] || [];
          return (
            <section key={b.key} className="pb-panel">
              <div className="pb-panel-head">
                <span className="pb-panel-title">{b.title}</span>
                <span className="pb-panel-sub">{b.sub}</span>
              </div>
              {rows.length === 0 ? (
                <div className="pb-empty">
                  {status === "loading" ? "Loading…"
                    : "No data yet — run a slate prep (cmc-daily.ps1) to populate."}
                </div>
              ) : (
                <table className="pb-table">
                  <thead><tr>{b.head.map((h, i) => <th key={i}>{h}</th>)}</tr></thead>
                  <tbody>
                    {rows.map((r, ri) => {
                      const cells = b.row(r);
                      return (
                        <tr key={ri}>
                          {cells.map((c, ci) => (
                            <td key={ci} className={ci === b.lead ? "pb-lead" : ci === 1 ? "pb-name" : ""}>
                              {c}
                            </td>
                          ))}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </section>
          );
        })}
      </div>

      <footer className="pb-foot">
        Model probabilities — not guarantees. Big parlays are long shots by design;
        pick the high-probability legs and bet small. CMC · honest data.
      </footer>
    </div>
  );
}

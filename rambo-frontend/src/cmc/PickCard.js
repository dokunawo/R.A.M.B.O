import React from "react";

// Team-color accent for the tile top strip + orb glow, keyed off the backend
// pick.glow ("gold" | "green" | "blue" | "red"). Falls back to gold.
const GLOW = {
  gold: "#d6a21e",
  green: "#39ff5a",
  blue: "#4ea0ff",
  red: "#ff5a5a",
};

const pct = (x) => `${x >= 0 ? "" : "−"}${Math.abs(x * 100).toFixed(1)}%`;

// One pick tile. Renders both moneyline "leans" (kind="ml") and prop "skip"
// states (kind="prop"). For ml the big number is the lean vs the market (green
// when meaningful, dim when negligible); for props it's the −EV edge (red).
export default function PickCard({ pick, rank, kind, king }) {
  const glow = GLOW[pick.glow] || GLOW.gold;
  const isML = kind === "ml";
  const edge = pick.edge;

  // ml: lean is positive; highlight green only if it's a meaningful (>3%) lean
  const edgeClass = isML ? (edge > 0.03 ? "" : "dim") : "neg";
  const edgeCap = isML ? "LEAN VS MKT" : "MODEL EDGE";

  const isLogo = (pick.headshot_url || "").includes("team-logos");

  return (
    <div className={`cmc-tile ${king ? "king" : ""} ${isML ? "" : "skip"}`}>
      <div className="cmc-strip" style={{ background: `linear-gradient(90deg, ${glow}, transparent)` }} />
      {king && <div className="cmc-king-badge">👑</div>}

      <div className="cmc-tile-top">
        <div className={`cmc-orb ${isLogo ? "logo" : ""}`} style={{ "--orb-glow": glow }}>
          {pick.headshot_url
            ? <img src={pick.headshot_url} alt="" onError={(e) => { e.target.style.display = "none"; }} />
            : <span className="cmc-initials">{pick.initials}</span>}
        </div>
        <div className="cmc-id">
          <div className="cmc-name">{pick.name}</div>
          <div className="cmc-matchup">
            {pick.team} <span className="hand">vs {pick.opponent}</span>
            {pick.hand ? <span className="hand"> · {pick.hand}HP</span> : null}
          </div>
        </div>
      </div>

      <div className="cmc-pick-label">{pick.pick}</div>

      <div className="cmc-statline">
        <div className={`cmc-edge ${edgeClass}`}>
          <span className="num">{pct(edge)}</span>
          <span className="cap">{edgeCap}</span>
        </div>
        <div className="cmc-probs">
          <div>MODEL <b>{Math.round(pick.model_p * 100)}%</b></div>
          <div>{isML ? "MKT" : "B/E"} <b>{Math.round(pick.breakeven * 100)}%</b></div>
          {!isML && pick.multiplier ? <div>MULT <b>{pick.multiplier}×</b></div> : null}
        </div>
      </div>

      {pick.support ? <div className="cmc-support">{pick.support}</div> : null}

      <div className="cmc-tags">
        {isML
          ? <span className="cmc-tag lean">LEAN</span>
          : <span className="cmc-tag skip">−EV · SKIP</span>}
        {typeof rank === "number" ? <span className="cmc-tag edge">#{rank + 1}</span> : null}
      </div>
    </div>
  );
}

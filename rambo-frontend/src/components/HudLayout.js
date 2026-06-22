import React from "react";
import "./HudLayout.css";

export default function HudLayout() {
  return (
    <div className="hud-container">

      {/* TOP ROW */}
      <div className="hud-row">
        <div className="hud-col">Top Left</div>
        <div className="hud-col">Top Center</div>
        <div className="hud-col">Top Right</div>
      </div>

      {/* MIDDLE ROW */}
      <div className="hud-row">
        <div className="hud-col">Middle Left</div>
        <div className="hud-col">Middle Center</div>
        <div className="hud-col">Middle Right</div>
      </div>

      {/* BOTTOM ROW */}
      <div className="hud-row">
        <div className="hud-col">Bottom Left</div>
        <div className="hud-col">Bottom Center</div>
        <div className="hud-col">Bottom Right</div>
      </div>

    </div>
  );
}

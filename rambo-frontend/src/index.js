import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import SplashScreen from "./components/SplashScreen";
import AgentPage from "./components/AgentPage";
import LearningLog from "./components/LearningLog";
import RoundTable from "./components/RoundTable";
import { armAutoStart } from "./components/screenVision";
import "./App.css";

// Arm screen-share auto-start at app load — BEFORE the Phase 1 intro mounts the
// command console — so the boot gesture (rambo-mediakeys.ahk) and the operator's
// first interaction reliably trigger it on the root route, not only on /console.
armAutoStart();

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <BrowserRouter>
    <div className="app-root">
      <Routes>
        <Route path="/" element={<SplashScreen />} />
        <Route path="/console" element={<SplashScreen skipIntro />} />
        <Route path="/agent/:agentKey" element={<AgentPage />} />
        <Route path="/learning" element={<LearningLog />} />
        <Route path="/council" element={<RoundTable />} />
      </Routes>
    </div>
  </BrowserRouter>
);

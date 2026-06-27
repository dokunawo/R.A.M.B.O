import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import SplashScreen from "./components/SplashScreen";
import AgentPage from "./components/AgentPage";
import LearningLog from "./components/LearningLog";
import RoundTable from "./components/RoundTable";
import HistoryPage from "./components/HistoryPage";
import ChancesMakeChampions from "./cmc/ChancesMakeChampions";
import EdgeCardPoster from "./cmc/EdgeCardPoster";
import { armAutoStart } from "./components/screenVision";
import "./App.css";

// Arm screen-share auto-start at app load — BEFORE the Phase 1 intro mounts the
// command console — so the boot gesture (rambo-mediakeys.ahk) and the operator's
// first interaction reliably trigger it on the root route, not only on /console.
armAutoStart();

// Tell the backend the UI has loaded and the screen-share listener is armed. The
// AHK boot gesture polls /ui/ready and clicks ONLY after this — so it never clicks
// on a blank, not-yet-loaded page. Ordering matters: arm first, then signal ready.
// Retry until the backend acks (at cold boot the backend may still be coming up).
(function signalUiReady(attempt) {
  fetch("http://localhost:8000/ui/ready", { method: "POST" })
    .then((r) => { if (!r.ok) throw new Error("not ok"); })
    .catch(() => { if (attempt < 60) setTimeout(() => signalUiReady(attempt + 1), 1000); });
})(0);

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
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/edge" element={<ChancesMakeChampions />} />
        <Route path="/card" element={<EdgeCardPoster />} />
        <Route path="/card/:market" element={<EdgeCardPoster />} />
      </Routes>
    </div>
  </BrowserRouter>
);

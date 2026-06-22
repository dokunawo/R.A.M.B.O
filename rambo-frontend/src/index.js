import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import SplashScreen from "./components/SplashScreen";
import AgentPage from "./components/AgentPage";
import LearningLog from "./components/LearningLog";
import RoundTable from "./components/RoundTable";
import "./App.css";

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

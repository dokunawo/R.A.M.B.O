import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import App from "./App";
import SplashScreen from "./components/SplashScreen";

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <BrowserRouter>
    <Routes>
      <Route path="/" element={<SplashScreen />} />
      <Route path="/hud" element={<App />} />
    </Routes>
  </BrowserRouter>
);

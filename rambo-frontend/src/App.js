import React, { useState, useEffect } from "react";
import "./App.css";
import SplashScreen from "./components/SplashScreen";
import HudLayout from "./components/HudLayout";

function App() {
  const [showSplash, setShowSplash] = useState(true);

  useEffect(() => {
    const timer = setTimeout(() => setShowSplash(false), 2500);
    return () => clearTimeout(timer);
  }, []);

  return (
    <div className="app-root">
      {showSplash ? <SplashScreen /> : <HudLayout />}
    </div>
  );
}

export default App;

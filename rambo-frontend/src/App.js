import React from "react";
import "./App.css";
import SplashScreen from "./components/SplashScreen";

// SplashScreen is now the full app: the boot sequence flows into a live,
// interactive console (command input + activity feed). The old HudLayout was
// only a placeholder scaffold, so we no longer swap to it after a timeout.
function App() {
  return (
    <div className="app-root">
      <SplashScreen />
    </div>
  );
}

export default App;

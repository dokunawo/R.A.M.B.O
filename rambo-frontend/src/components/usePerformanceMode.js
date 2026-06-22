import { useState, useEffect, useCallback, useRef } from "react";

export default function usePerformanceMode() {
  const [perfMode, setPerfMode] = useState("full");
  const batteryRef = useRef(null);

  const evaluate = useCallback(() => {
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reducedMotion) { setPerfMode("minimal"); return; }

    const bat = batteryRef.current;
    if (bat && !bat.charging && bat.level < 0.2) { setPerfMode("low"); return; }

    if (document.hidden) { setPerfMode("low"); return; }

    setPerfMode("full");
  }, []);

  useEffect(() => {
    evaluate();

    const mqHandler = () => evaluate();
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    mq.addEventListener("change", mqHandler);

    const visHandler = () => evaluate();
    document.addEventListener("visibilitychange", visHandler);

    if (navigator.getBattery) {
      navigator.getBattery().then((bat) => {
        batteryRef.current = bat;
        bat.addEventListener("chargingchange", evaluate);
        bat.addEventListener("levelchange", evaluate);
        evaluate();
      }).catch(() => {});
    }

    return () => {
      mq.removeEventListener("change", mqHandler);
      document.removeEventListener("visibilitychange", visHandler);
      const bat = batteryRef.current;
      if (bat) {
        bat.removeEventListener("chargingchange", evaluate);
        bat.removeEventListener("levelchange", evaluate);
      }
    };
  }, [evaluate]);

  return {
    perfMode,
    isLow: perfMode === "low" || perfMode === "minimal",
    isMinimal: perfMode === "minimal",
    bloomEnabled: perfMode === "full",
    particleScale: perfMode === "full" ? 1 : perfMode === "low" ? 0.4 : 0,
    dpr: perfMode === "full" ? [1, 1.5] : [1, 1],
  };
}

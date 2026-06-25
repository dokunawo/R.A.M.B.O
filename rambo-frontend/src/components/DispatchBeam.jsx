import React, { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

const ORBIT_RADIUS = 2.8;
const ORBIT_TILT   = 0.3;
const ORBIT_SPEED  = 0.08;
const BEAM_DURATION = 1.6;

// Indices + colors mirror the AgentConstellation lineup order (6 nodes) so
// dispatch beams point at the right orbiting node.
const AGENT_INDICES = {
  planner: 0, executor: 1, researcher: 2, keeper: 3, sentinel: 4, pilot: 5,
};
const TOTAL = 6;

const AGENT_COLORS = {
  planner: "#7b6ff0", executor: "#f59e0b", researcher: "#06b6d4",
  keeper: "#10b981", sentinel: "#ef4444", pilot: "#ec4899",
};

function getAgentPosition(key, elapsedTime) {
  const i = AGENT_INDICES[key] ?? 0;
  const angle = (i / TOTAL) * Math.PI * 2 + elapsedTime * ORBIT_SPEED;
  return [
    Math.cos(angle) * ORBIT_RADIUS,
    Math.sin(angle + i) * ORBIT_TILT * ORBIT_RADIUS * 0.3,
    Math.sin(angle) * ORBIT_RADIUS,
  ];
}

function DynamicBeam({ agentKey, onComplete }) {
  const tubeRef = useRef();
  const startTime = useRef(-1);
  const color = AGENT_COLORS[agentKey] || "#e8b15a";

  const material = useMemo(() => new THREE.MeshBasicMaterial({
    color: new THREE.Color(color),
    transparent: true,
    opacity: 0.6,
    depthWrite: false,
    depthTest: false,
    blending: THREE.AdditiveBlending,
    side: THREE.DoubleSide,
  }), [color]);

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    if (startTime.current < 0) startTime.current = t;
    const elapsed = t - startTime.current;
    const progress = Math.min(elapsed / BEAM_DURATION, 1.0);

    const target = getAgentPosition(agentKey, t);
    const targetV = new THREE.Vector3(...target);
    const origin = new THREE.Vector3(0, 0, 0);
    const current = origin.clone().lerp(targetV, Math.min(progress * 1.5, 1.0));
    const length = origin.distanceTo(current);

    if (tubeRef.current && length > 0.01) {
      const mid = origin.clone().lerp(current, 0.5);
      tubeRef.current.position.copy(mid);
      const dir = current.clone().sub(origin).normalize();
      const q = new THREE.Quaternion();
      q.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
      tubeRef.current.quaternion.copy(q);
      tubeRef.current.scale.set(1, length, 1);
    }

    if (progress > 0.6) {
      material.opacity = 0.6 * (1.0 - (progress - 0.6) / 0.4);
    }

    if (progress >= 1.0) onComplete?.();
  });

  return (
    <mesh ref={tubeRef} material={material}>
      <cylinderGeometry args={[0.015, 0.025, 1, 6, 1]} />
    </mesh>
  );
}

export default function DispatchBeams({ dispatches, onBeamComplete }) {
  return (
    <group>
      {dispatches.map((d) => (
        <DynamicBeam
          key={d.id}
          agentKey={d.agentKey}
          onComplete={() => onBeamComplete?.(d.id)}
        />
      ))}
    </group>
  );
}

// AgentConstellation.jsx — Tier 4: agent nodes orbiting the cosmic orb
// as a floating 3D constellation with status-driven glow and depth-fading labels.
import React, { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

// Consolidated lineup — 3 routable modes + keeper/sentinel/pilot services.
const AGENTS = [
  { key: "planner",    label: "PLANNER",     color: "#7b6ff0" },
  { key: "executor",   label: "EXECUTOR",    color: "#f59e0b" },
  { key: "researcher", label: "RESEARCHER",  color: "#06b6d4" },
  { key: "keeper",     label: "KEEPER",      color: "#10b981" },
  { key: "sentinel",   label: "SENTINEL",    color: "#ef4444" },
  { key: "pilot",      label: "PILOT",       color: "#ec4899" },
];

const ORBIT_RADIUS = 2.8;
const ORBIT_TILT   = 0.3;    // radians — tilted ring
const ORBIT_SPEED  = 0.08;   // radians per second

const STATUS_COLORS = {
  idle:    new THREE.Color("#4a90a4"),
  active:  new THREE.Color("#22c55e"),
  offline: new THREE.Color("#6b7280"),
};

// Glow sprite shader for each agent node
const nodeVert = /* glsl */ `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

const nodeFrag = /* glsl */ `
precision highp float;
uniform vec3 uColor;
uniform float uPulse;
varying vec2 vUv;
void main() {
  vec2 c = vUv - 0.5;
  float d = length(c) * 2.0;
  // Core dot
  float core = smoothstep(0.45, 0.15, d);
  // Outer glow ring
  float ring = smoothstep(1.0, 0.4, d) * smoothstep(0.0, 0.3, d);
  float pulse = 0.7 + 0.3 * uPulse;
  float alpha = (core * 0.9 + ring * 0.25) * pulse;
  vec3 col = uColor * (core * 1.4 + ring * 0.6);
  gl_FragColor = vec4(col, alpha);
}
`;

// Label texture — renders agent name into a canvas texture
function makeLabelTexture(text, color) {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 48;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, 256, 48);
  ctx.font = "bold 20px 'JetBrains Mono', monospace";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = color;
  ctx.globalAlpha = 0.85;
  ctx.fillText(text, 128, 24);
  const tex = new THREE.CanvasTexture(canvas);
  tex.minFilter = THREE.LinearFilter;
  tex.magFilter = THREE.LinearFilter;
  return tex;
}

function AgentNode({ agent, index, total, statusMap }) {
  const meshRef = useRef();
  const labelRef = useRef();

  const material = useMemo(() => new THREE.ShaderMaterial({
    vertexShader: nodeVert,
    fragmentShader: nodeFrag,
    uniforms: {
      uColor: { value: new THREE.Color(agent.color) },
      uPulse: { value: 1.0 },
    },
    transparent: true,
    depthWrite: false,
    depthTest: false,
    blending: THREE.AdditiveBlending,
    side: THREE.DoubleSide,
  }), [agent.color]);

  const labelTexture = useMemo(() => makeLabelTexture(agent.label, agent.color), [agent.label, agent.color]);

  const labelMaterial = useMemo(() => new THREE.MeshBasicMaterial({
    map: labelTexture,
    transparent: true,
    depthWrite: false,
    depthTest: false,
    blending: THREE.NormalBlending,
    side: THREE.DoubleSide,
    opacity: 0.8,
  }), [labelTexture]);

  useFrame(({ clock, camera }) => {
    const t = clock.getElapsedTime();
    const angle = (index / total) * Math.PI * 2 + t * ORBIT_SPEED;

    const x = Math.cos(angle) * ORBIT_RADIUS;
    const z = Math.sin(angle) * ORBIT_RADIUS;
    const y = Math.sin(angle + index) * ORBIT_TILT * ORBIT_RADIUS * 0.3;

    if (meshRef.current) {
      meshRef.current.position.set(x, y, z);
      meshRef.current.quaternion.copy(camera.quaternion);
    }
    if (labelRef.current) {
      labelRef.current.position.set(x, y - 0.28, z);
      labelRef.current.quaternion.copy(camera.quaternion);

      // Depth fade — labels closer to camera are brighter
      const dist = labelRef.current.position.distanceTo(camera.position);
      const fade = THREE.MathUtils.smoothstep(dist, 3, 7);
      labelMaterial.opacity = 0.85 * (1 - fade * 0.6);
    }

    // Pulse based on status
    const status = statusMap?.[agent.key] || "idle";
    const target = status === "active" ? 1.0 : status === "offline" ? 0.3 : 0.7;
    const current = material.uniforms.uPulse.value;
    material.uniforms.uPulse.value += (target - current) * 0.05;

    // Update color based on status
    const statusColor = STATUS_COLORS[status] || STATUS_COLORS.idle;
    const agentColor = new THREE.Color(agent.color);
    material.uniforms.uColor.value.copy(agentColor).lerp(statusColor, 0.3);
  });

  return (
    <>
      <mesh ref={meshRef} material={material} renderOrder={5}>
        <planeGeometry args={[0.32, 0.32]} />
      </mesh>
      <mesh ref={labelRef} material={labelMaterial} renderOrder={6}>
        <planeGeometry args={[0.8, 0.15]} />
      </mesh>
    </>
  );
}

// Orbit ring — faint golden ellipse showing the constellation path
function ConstellationRing() {
  const ref = useRef();
  const geometry = useMemo(() => {
    const pts = [];
    const segments = 96;
    for (let i = 0; i <= segments; i++) {
      const a = (i / segments) * Math.PI * 2;
      const x = Math.cos(a) * ORBIT_RADIUS;
      const z = Math.sin(a) * ORBIT_RADIUS;
      const y = Math.sin(a) * ORBIT_TILT * ORBIT_RADIUS * 0.15;
      pts.push(x, y, z);
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.Float32BufferAttribute(pts, 3));
    return geo;
  }, []);

  const material = useMemo(() => new THREE.LineBasicMaterial({
    color: new THREE.Color("#e8b15a"),
    transparent: true,
    opacity: 0.06,
    depthWrite: false,
    depthTest: false,
    blending: THREE.AdditiveBlending,
  }), []);

  useFrame(({ clock }) => {
    if (ref.current) {
      ref.current.rotation.y = clock.getElapsedTime() * 0.01;
    }
  });

  return <line ref={ref} geometry={geometry} material={material} renderOrder={4} />;
}

// Connection lines from orb center to each agent
function ConstellationLinks({ statusMap }) {
  const ref = useRef();
  const lineCount = AGENTS.length;

  const material = useMemo(() => new THREE.LineBasicMaterial({
    color: new THREE.Color("#e8b15a"),
    transparent: true,
    opacity: 0.04,
    depthWrite: false,
    depthTest: false,
    blending: THREE.AdditiveBlending,
  }), []);

  const geometry = useMemo(() => {
    const positions = new Float32Array(lineCount * 6);
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    return geo;
  }, [lineCount]);

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    const posArr = geometry.attributes.position.array;
    for (let i = 0; i < AGENTS.length; i++) {
      const angle = (i / AGENTS.length) * Math.PI * 2 + t * ORBIT_SPEED;
      const x = Math.cos(angle) * ORBIT_RADIUS;
      const z = Math.sin(angle) * ORBIT_RADIUS;
      const y = Math.sin(angle + i) * ORBIT_TILT * ORBIT_RADIUS * 0.3;
      // From center
      posArr[i * 6]     = 0;
      posArr[i * 6 + 1] = 0;
      posArr[i * 6 + 2] = 0;
      // To agent
      posArr[i * 6 + 3] = x;
      posArr[i * 6 + 4] = y;
      posArr[i * 6 + 5] = z;
    }
    geometry.attributes.position.needsUpdate = true;
  });

  return <lineSegments ref={ref} geometry={geometry} material={material} renderOrder={3} />;
}

export default function AgentConstellation({ statusMap = {} }) {
  return (
    <group>
      <ConstellationRing />
      <ConstellationLinks statusMap={statusMap} />
      {AGENTS.map((agent, i) => (
        <AgentNode key={agent.key} agent={agent} index={i} total={AGENTS.length} statusMap={statusMap} />
      ))}
    </group>
  );
}

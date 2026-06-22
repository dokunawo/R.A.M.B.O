// CosmicBackground.jsx — Tier 2: deep-space nebula, twinkling stars,
// distant node web, warm glow pool behind the orb.
// Renders inside the same Canvas as CosmicOrb, at negative renderOrder.
import React, { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

function mulberry32(seed) {
  return () => {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ---------- 1. STARFIELD ----------
const STAR_COUNT = 500;

function Starfield() {
  const { positions, sizes, phases } = useMemo(() => {
    const rand = mulberry32(42);
    const pos = new Float32Array(STAR_COUNT * 3);
    const sz  = new Float32Array(STAR_COUNT);
    const ph  = new Float32Array(STAR_COUNT);
    for (let i = 0; i < STAR_COUNT; i++) {
      pos[i * 3]     = (rand() - 0.5) * 30;
      pos[i * 3 + 1] = (rand() - 0.5) * 30;
      pos[i * 3 + 2] = -rand() * 14 - 3;
      sz[i]  = 0.4 + rand() * 1.2;
      ph[i]  = rand() * Math.PI * 2;
    }
    return { positions: pos, sizes: sz, phases: ph };
  }, []);

  const material = useMemo(() => new THREE.ShaderMaterial({
    vertexShader: /* glsl */ `
      attribute float aSize;
      attribute float aPhase;
      varying float vAlpha;
      uniform float uTime;
      void main() {
        vec4 mvPos = modelViewMatrix * vec4(position, 1.0);
        float twinkle = 0.5 + 0.5 * sin(uTime * (0.8 + aPhase * 0.6) + aPhase * 6.28);
        vAlpha = mix(0.08, 0.55, twinkle);
        gl_PointSize = aSize * (200.0 / -mvPos.z);
        gl_Position = projectionMatrix * mvPos;
      }
    `,
    fragmentShader: /* glsl */ `
      precision highp float;
      varying float vAlpha;
      void main() {
        float d = length(gl_PointCoord - 0.5) * 2.0;
        float disc = smoothstep(1.0, 0.4, d);
        gl_FragColor = vec4(0.8, 0.78, 0.9, disc * vAlpha);
      }
    `,
    uniforms: { uTime: { value: 0 } },
    transparent: true,
    depthWrite: false,
    depthTest: false,
    blending: THREE.AdditiveBlending,
  }), []);

  useFrame(({ clock }) => {
    material.uniforms.uTime.value = clock.getElapsedTime();
  });

  const geometry = useMemo(() => {
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geo.setAttribute("aSize",    new THREE.BufferAttribute(sizes, 1));
    geo.setAttribute("aPhase",   new THREE.BufferAttribute(phases, 1));
    return geo;
  }, [positions, sizes, phases]);

  return <points geometry={geometry} material={material} renderOrder={-10} />;
}

// ---------- 2. NEBULA CLOUDS ----------
const nebulaFrag = /* glsl */ `
precision highp float;
uniform float uTime;
varying vec2 vUv;

float hash(vec2 p) {
  return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}
float noise2d(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  float a = hash(i);
  float b = hash(i + vec2(1.0, 0.0));
  float c = hash(i + vec2(0.0, 1.0));
  float d = hash(i + vec2(1.0, 1.0));
  return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}
float fbm(vec2 p) {
  float v = 0.0, a = 0.5;
  for (int i = 0; i < 5; i++) {
    v += a * noise2d(p);
    p *= 2.1;
    a *= 0.48;
  }
  return v;
}

void main() {
  vec2 uv = vUv - 0.5;
  float t = uTime * 0.012;

  float n1 = fbm(uv * 2.5 + t * 0.3);
  float n2 = fbm(uv * 4.0 - t * 0.2 + 42.0);
  float n3 = fbm(uv * 7.0 + t * 0.15 - 17.0);

  vec3 warm = vec3(0.35, 0.18, 0.05);
  vec3 cool = vec3(0.08, 0.05, 0.18);
  vec3 teal = vec3(0.03, 0.12, 0.15);

  float blend = n1 * 0.5 + n2 * 0.3 + n3 * 0.2;
  vec3 color = mix(cool, warm, smoothstep(0.3, 0.7, blend));
  color = mix(color, teal, smoothstep(0.55, 0.75, n2) * 0.3);

  // circular radial fade — must hit zero well before quad edge
  float dist = length(uv) * 2.0;
  float radial = smoothstep(1.0, 0.15, dist);
  float alpha = blend * radial * 0.12;

  gl_FragColor = vec4(color, alpha);
}
`;

function NebulaClouds() {
  const ref = useRef();
  const material = useMemo(() => new THREE.ShaderMaterial({
    vertexShader: /* glsl */ `
      varying vec2 vUv;
      void main() {
        vUv = uv;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: nebulaFrag,
    uniforms: { uTime: { value: 0 } },
    transparent: true,
    depthWrite: false,
    depthTest: false,
    blending: THREE.AdditiveBlending,
    side: THREE.DoubleSide,
  }), []);

  useFrame(({ clock, camera }) => {
    material.uniforms.uTime.value = clock.getElapsedTime();
    if (ref.current) ref.current.quaternion.copy(camera.quaternion);
  });

  return (
    <mesh ref={ref} material={material} position={[0, 0, -5]} renderOrder={-9}>
      <planeGeometry args={[20, 20]} />
    </mesh>
  );
}

// ---------- 3. DISTANT NODE WEB ----------
const NODE_COUNT = 24;
const CONNECT_DIST = 3.8;

function NodeWeb() {
  const { nodePositions, linePositions, nodePhases } = useMemo(() => {
    const rand = mulberry32(1337);
    const nodes = [];
    for (let i = 0; i < NODE_COUNT; i++) {
      nodes.push(
        (rand() - 0.5) * 16,
        (rand() - 0.5) * 16,
        -(rand() * 5 + 4),
      );
    }
    const lines = [];
    for (let i = 0; i < NODE_COUNT; i++) {
      for (let j = i + 1; j < NODE_COUNT; j++) {
        const dx = nodes[i*3] - nodes[j*3];
        const dy = nodes[i*3+1] - nodes[j*3+1];
        const dz = nodes[i*3+2] - nodes[j*3+2];
        if (Math.sqrt(dx*dx + dy*dy + dz*dz) < CONNECT_DIST) {
          lines.push(
            nodes[i*3], nodes[i*3+1], nodes[i*3+2],
            nodes[j*3], nodes[j*3+1], nodes[j*3+2],
          );
        }
      }
    }
    const ph = new Float32Array(NODE_COUNT);
    for (let i = 0; i < NODE_COUNT; i++) ph[i] = rand() * Math.PI * 2;
    return {
      nodePositions: new Float32Array(nodes),
      linePositions: new Float32Array(lines),
      nodePhases: ph,
    };
  }, []);

  const nodeMat = useMemo(() => new THREE.ShaderMaterial({
    vertexShader: /* glsl */ `
      attribute float aPhase;
      varying float vAlpha;
      uniform float uTime;
      void main() {
        vec4 mvPos = modelViewMatrix * vec4(position, 1.0);
        float pulse = 0.5 + 0.5 * sin(uTime * 0.5 + aPhase * 6.28);
        vAlpha = mix(0.1, 0.45, pulse);
        gl_PointSize = mix(1.5, 3.0, pulse) * (200.0 / -mvPos.z);
        gl_Position = projectionMatrix * mvPos;
      }
    `,
    fragmentShader: /* glsl */ `
      precision highp float;
      varying float vAlpha;
      void main() {
        float d = length(gl_PointCoord - 0.5) * 2.0;
        float disc = smoothstep(1.0, 0.2, d);
        gl_FragColor = vec4(0.91, 0.69, 0.35, disc * vAlpha);
      }
    `,
    uniforms: { uTime: { value: 0 } },
    transparent: true, depthWrite: false, depthTest: false,
    blending: THREE.AdditiveBlending,
  }), []);

  const lineMat = useMemo(() => new THREE.ShaderMaterial({
    vertexShader: `void main() { gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
    fragmentShader: `precision highp float; void main() { gl_FragColor = vec4(0.91, 0.69, 0.35, 0.04); }`,
    transparent: true, depthWrite: false, depthTest: false,
    blending: THREE.AdditiveBlending,
  }), []);

  const nodeGeo = useMemo(() => {
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(nodePositions, 3));
    geo.setAttribute("aPhase",   new THREE.BufferAttribute(nodePhases, 1));
    return geo;
  }, [nodePositions, nodePhases]);

  const lineGeo = useMemo(() => {
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(linePositions, 3));
    return geo;
  }, [linePositions]);

  useFrame(({ clock }) => { nodeMat.uniforms.uTime.value = clock.getElapsedTime(); });

  return (
    <group renderOrder={-8}>
      <points geometry={nodeGeo} material={nodeMat} />
      <lineSegments geometry={lineGeo} material={lineMat} />
    </group>
  );
}

// ---------- 4. GLOW POOL ----------
function GlowPool() {
  const ref = useRef();
  const material = useMemo(() => new THREE.ShaderMaterial({
    vertexShader: /* glsl */ `
      varying vec2 vUv;
      void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }
    `,
    fragmentShader: /* glsl */ `
      precision highp float;
      uniform vec3 uColor;
      uniform float uTime;
      varying vec2 vUv;
      void main() {
        vec2 c = vUv - 0.5;
        float d = length(c) * 2.0;
        float glow = exp(-d * d * 4.0);
        glow *= 0.9 + 0.1 * sin(uTime * 0.5);
        // hard circular cutoff well before quad edge
        glow *= smoothstep(0.95, 0.5, d);
        gl_FragColor = vec4(uColor, glow * 0.15);
      }
    `,
    uniforms: {
      uColor: { value: new THREE.Color(0.5, 0.28, 0.08) },
      uTime:  { value: 0 },
    },
    transparent: true, depthWrite: false, depthTest: false,
    blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
  }), []);

  useFrame(({ clock, camera }) => {
    material.uniforms.uTime.value = clock.getElapsedTime();
    if (ref.current) ref.current.quaternion.copy(camera.quaternion);
  });

  return (
    <mesh ref={ref} material={material} position={[0, 0, -2]} renderOrder={-7}>
      <planeGeometry args={[10, 10]} />
    </mesh>
  );
}

export default function CosmicBackground() {
  return (
    <>
      <Starfield />
      <NebulaClouds />
      <NodeWeb />
      <GlowPool />
    </>
  );
}

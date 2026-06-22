// RamboOrb3D.jsx
import React, { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

import {
  ramboOrbVertexShader,
  ramboOrbFragmentShader,
  ramboOrbLineVertexShader,
  ramboOrbLineFragmentShader,
  ramboPlasmaVertexShader,
  ramboPlasmaFragmentShader,
} from "./RamboOrbShaders";

// Fewer particles on small screens for performance (LOD).
const PARTICLE_COUNT =
  (typeof window !== "undefined" && window.innerWidth < 768) ? 1800 : 4000;
const ORB_RADIUS = 1.8;

// Nudge this by eye — world units for the plasma nucleus radius
const CORE_SIZE = ORB_RADIUS * 0.78; // ~1.4

const SHOW_CORE = true;
const SHOW_CONNECTIONS = false;

const CONNECTION_COUNT = 110;
const CONNECTION_MAX_DIST = 0.5;

const CAMERA_DISTANCE = 4.2;

// Shared breathing frequency — all elements pulse as one
const BREATH_FREQ = 1.8;

/* ---------------- geometry builders ---------------- */

function buildParticleGeometry() {
  const positions = new Float32Array(PARTICLE_COUNT * 3);
  const randoms = new Float32Array(PARTICLE_COUNT);
  const phases = new Float32Array(PARTICLE_COUNT);

  for (let i = 0; i < PARTICLE_COUNT; i++) {
    // Soft volumetric distribution instead of a thin hard-edged shell:
    //  - a main body that fills 0.45R→1.0R (no hollow center, no sharp ring)
    //  - a sparse, cubed-falloff tail reaching ~1.45R so the edge dissolves
    //    into wisps rather than terminating in a crisp circle.
    const body = 0.45 + 0.55 * Math.pow(Math.random(), 0.7);
    const tail = Math.pow(Math.random(), 3.0) * 0.45;
    const r = ORB_RADIUS * (body + tail);

    const theta = Math.acos(2 * Math.random() - 1.0);
    const phi = Math.random() * Math.PI * 2.0;

    const x = r * Math.sin(theta) * Math.cos(phi);
    const y = r * Math.sin(theta) * Math.sin(phi);
    const z = r * Math.cos(theta);

    positions.set([x, y, z], i * 3);
    randoms[i] = Math.random();
    phases[i] = Math.random();
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute("aRandom", new THREE.BufferAttribute(randoms, 1));
  geometry.setAttribute("aPhase", new THREE.BufferAttribute(phases, 1));
  return geometry;
}

function buildConnectionGeometry(particleGeometry) {
  const pos = particleGeometry.getAttribute("position");
  const positions = [];

  for (let i = 0; i < CONNECTION_COUNT; i++) {
    const a = Math.floor(Math.random() * PARTICLE_COUNT);
    let b = -1;
    let attempts = 0;

    while (attempts < 16) {
      const candidate = Math.floor(Math.random() * PARTICLE_COUNT);
      const dx = pos.getX(a) - pos.getX(candidate);
      const dy = pos.getY(a) - pos.getY(candidate);
      const dz = pos.getZ(a) - pos.getZ(candidate);
      const dist = Math.sqrt(dx * dx + dy * dy + dz * dz);

      if (candidate !== a && dist < CONNECTION_MAX_DIST) {
        b = candidate;
        break;
      }
      attempts++;
    }

    if (b !== -1) {
      positions.push(
        pos.getX(a), pos.getY(a), pos.getZ(a),
        pos.getX(b), pos.getY(b), pos.getZ(b)
      );
    }
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute(
    "position",
    new THREE.BufferAttribute(new Float32Array(positions), 3)
  );
  return geometry;
}

/* ---------------- sub-components ---------------- */

// Particles — no per-mesh mouse parallax; group handles it now
function RamboOrbPoints({ geometry, colorOuter, colorCore }) {
  const material = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: ramboOrbVertexShader,
        fragmentShader: ramboOrbFragmentShader,
        uniforms: {
          uTime: { value: 0 },
          uPixelRatio: { value: Math.min(window.devicePixelRatio, window.innerWidth < 768 ? 1.5 : 2) },
          uBaseSize: { value: 2.6 },
          uRotationSpeed: { value: 0.06 },
          uPerspective: { value: CAMERA_DISTANCE },
          uColor: { value: new THREE.Color(colorOuter) },
          uColorCore: { value: new THREE.Color(colorCore) },
        },
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    [colorOuter, colorCore]
  );

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    material.uniforms.uTime.value = t;
    // Synced breathing: same frequency as the plasma core
    material.uniforms.uBaseSize.value = 2.6 + Math.sin(t * BREATH_FREQ) * 0.4;
  });

  return <points geometry={geometry} material={material} />;
}

function RamboOrbLines({ geometry, color, opacity }) {
  const material = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: ramboOrbLineVertexShader,
        fragmentShader: ramboOrbLineFragmentShader,
        uniforms: {
          uTime: { value: 0 },
          uRotationSpeed: { value: 0.06 },
          uColor: { value: new THREE.Color(color) },
          uOpacity: { value: opacity },
        },
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    [color, opacity]
  );

  useFrame(({ clock }) => {
    material.uniforms.uTime.value = clock.getElapsedTime();
  });

  return <lineSegments geometry={geometry} material={material} />;
}

// Plasma nucleus — billboarded quad with fbm noise.
// Lives OUTSIDE the parallax group so it stays centered as a stable anchor.
function PlasmaCore({ colorCore }) {
  const ref = useRef();
  const material = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: ramboPlasmaVertexShader,
        fragmentShader: ramboPlasmaFragmentShader,
        uniforms: {
          uTime: { value: 0 },
          uBreath: { value: 0 },
          uColor: { value: new THREE.Color(colorCore) },
        },
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        side: THREE.DoubleSide,
      }),
    [colorCore]
  );

  useFrame(({ clock, camera }) => {
    const t = clock.getElapsedTime();
    material.uniforms.uTime.value = t;
    // Synced breathing: 0→1 oscillation on same curve as particles
    material.uniforms.uBreath.value = (Math.sin(t * BREATH_FREQ) + 1.0) * 0.5;
    // Billboard: always face camera
    if (ref.current) ref.current.quaternion.copy(camera.quaternion);
  });

  return (
    <mesh ref={ref} material={material}>
      <planeGeometry args={[CORE_SIZE * 2, CORE_SIZE * 2]} />
    </mesh>
  );
}

/* ---------------- main export ---------------- */

export default function RamboOrb3D({
  colorOuter = "#caa46b",
  colorCore = "#fff4da",
  colorRing = "#d9a857",
  mouseRef = null,
}) {
  const particleGeometry = useMemo(() => buildParticleGeometry(), []);
  const connectionGeometry = useMemo(
    () => (SHOW_CONNECTIONS ? buildConnectionGeometry(particleGeometry) : null),
    [particleGeometry]
  );

  // Group ref for cursor parallax — tilts the dust/ring/spoke shell
  const groupRef = useRef();
  useFrame(() => {
    if (!groupRef.current || !mouseRef?.current) return;
    const { x, y } = mouseRef.current;
    groupRef.current.rotation.y += (x * 0.06 - groupRef.current.rotation.y) * 0.04;
    groupRef.current.rotation.x += (-y * 0.06 - groupRef.current.rotation.x) * 0.04;
  });

  return (
    <>
      {/* Plasma core is outside the parallax group — stable anchor at center */}
      {SHOW_CORE && <PlasmaCore colorCore={colorCore} />}

      {/* Dust cloud + rings + spokes tilt with mouse */}
      <group ref={groupRef}>
        <RamboOrbPoints geometry={particleGeometry} colorOuter={colorOuter} colorCore={colorCore} />

        {SHOW_CONNECTIONS && connectionGeometry && (
          <RamboOrbLines geometry={connectionGeometry} color={colorRing} opacity={0.16} />
        )}
      </group>
    </>
  );
}

// CosmicOrb.jsx — Tier 1+3: wireframe icosahedron with noise displacement,
// fresnel rim glow, billboarded glow halo, voice reactivity.
import React, { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import {
  cosmicOrbVertexShader,
  cosmicOrbFragmentShader,
} from "./CosmicOrbShaders";

const ORB_RADIUS = 1.6;
const DETAIL = 18;

const GOLD = new THREE.Color("#e8b15a");
const GOLD_GLOW = new THREE.Color("#ffd98a");

const glowSpriteVert = /* glsl */ `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

const glowSpriteFrag = /* glsl */ `
precision highp float;
uniform vec3 uColor;
uniform float uIntensity;
uniform float uAudioLevel;
varying vec2 vUv;
void main() {
  vec2 c = vUv - 0.5;
  float d = length(c) * 2.0;
  float glow = smoothstep(1.0, 0.3, d) * smoothstep(0.0, 0.25, d);
  // Audio expands and brightens the halo
  float audioBright = 1.0 + uAudioLevel * 0.8;
  glow = pow(glow, 1.5) * uIntensity * audioBright;
  gl_FragColor = vec4(uColor * 1.2, glow);
}
`;

function WireframeOrb({ audioLevelRef }) {
  const geometry = useMemo(() => {
    const geo = new THREE.IcosahedronGeometry(ORB_RADIUS, DETAIL);
    geo.computeVertexNormals();
    return geo;
  }, []);

  const material = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: cosmicOrbVertexShader,
        fragmentShader: cosmicOrbFragmentShader,
        uniforms: {
          uTime: { value: 0 },
          uNoiseScale: { value: 1.2 },
          uNoiseStrength: { value: 0.12 },
          uBreathSpeed: { value: 1.0 },
          uColor: { value: GOLD.clone() },
          uOpacity: { value: 0.45 },
          uFresnelPower: { value: 1.8 },
          uFresnelBias: { value: 0.1 },
          uAudioLevel: { value: 0 },
        },
        wireframe: true,
        transparent: true,
        depthWrite: false,
        depthTest: false,
        blending: THREE.AdditiveBlending,
        side: THREE.DoubleSide,
        toneMapped: false,
      }),
    []
  );

  useFrame(({ clock }) => {
    material.uniforms.uTime.value = clock.getElapsedTime();
    material.uniforms.uAudioLevel.value = audioLevelRef?.current ?? 0;
  });

  return <mesh geometry={geometry} material={material} />;
}

function GlowHalo({ audioLevelRef }) {
  const ref = useRef();

  const material = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: glowSpriteVert,
        fragmentShader: glowSpriteFrag,
        uniforms: {
          uColor: { value: GOLD_GLOW.clone() },
          uIntensity: { value: 0.2 },
          uAudioLevel: { value: 0 },
        },
        transparent: true,
        depthWrite: false,
        depthTest: false,
        blending: THREE.AdditiveBlending,
        side: THREE.DoubleSide,
        toneMapped: false,
      }),
    []
  );

  useFrame(({ camera }) => {
    if (ref.current) ref.current.quaternion.copy(camera.quaternion);
    material.uniforms.uAudioLevel.value = audioLevelRef?.current ?? 0;
  });

  const size = ORB_RADIUS * 2.8;
  return (
    <mesh ref={ref} material={material} renderOrder={-1}>
      <planeGeometry args={[size, size]} />
    </mesh>
  );
}

export default function CosmicOrb({ mouseRef = null, audioLevelRef = null }) {
  const groupRef = useRef();
  // Internal fallback ref when no external audio — .current must be a number
  const fallbackRef = useRef(0);
  const effectiveAudioRef = audioLevelRef || fallbackRef;

  useFrame(({ clock }) => {
    if (!groupRef.current) return;
    const t = clock.getElapsedTime();

    groupRef.current.rotation.y = t * 0.04;
    groupRef.current.rotation.x = Math.sin(t * 0.02) * 0.15;

    if (mouseRef?.current) {
      const { x, y } = mouseRef.current;
      groupRef.current.rotation.y += x * 0.06;
      groupRef.current.rotation.x += -y * 0.06;
    }
  });

  return (
    <>
      <GlowHalo audioLevelRef={effectiveAudioRef} />
      <group ref={groupRef}>
        <WireframeOrb audioLevelRef={effectiveAudioRef} />
      </group>
    </>
  );
}

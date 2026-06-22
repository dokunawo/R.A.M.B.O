// CosmicOrb.jsx — Tier 1: wireframe icosahedron with noise displacement,
// fresnel rim glow, billboarded glow halo, slow two-axis tumble.
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

// Glow halo as a camera-facing sprite — no depth/face artifacts
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
varying vec2 vUv;
void main() {
  vec2 c = vUv - 0.5;
  float d = length(c) * 2.0;
  // soft radial falloff — bright core ring, fades outward
  float glow = smoothstep(1.0, 0.3, d) * smoothstep(0.0, 0.25, d);
  glow = pow(glow, 1.5) * uIntensity;
  gl_FragColor = vec4(uColor * 1.2, glow);
}
`;

function WireframeOrb() {
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
          uOpacity: { value: 0.7 },
          uFresnelPower: { value: 1.8 },
          uFresnelBias: { value: 0.1 },
        },
        wireframe: true,
        transparent: true,
        depthWrite: false,
        depthTest: false,
        blending: THREE.AdditiveBlending,
        side: THREE.DoubleSide,
      }),
    []
  );

  useFrame(({ clock }) => {
    material.uniforms.uTime.value = clock.getElapsedTime();
  });

  return <mesh geometry={geometry} material={material} />;
}

function GlowHalo() {
  const ref = useRef();

  const material = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: glowSpriteVert,
        fragmentShader: glowSpriteFrag,
        uniforms: {
          uColor: { value: GOLD_GLOW.clone() },
          uIntensity: { value: 0.5 },
        },
        transparent: true,
        depthWrite: false,
        depthTest: false,
        blending: THREE.AdditiveBlending,
        side: THREE.DoubleSide,
      }),
    []
  );

  // Billboard: always face the camera
  useFrame(({ camera }) => {
    if (ref.current) ref.current.quaternion.copy(camera.quaternion);
  });

  const size = ORB_RADIUS * 3.6;
  return (
    <mesh ref={ref} material={material} renderOrder={-1}>
      <planeGeometry args={[size, size]} />
    </mesh>
  );
}

export default function CosmicOrb({ mouseRef = null }) {
  const groupRef = useRef();

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
      {/* Glow halo sits behind the orb, always facing camera */}
      <GlowHalo />
      <group ref={groupRef}>
        <WireframeOrb />
      </group>
    </>
  );
}

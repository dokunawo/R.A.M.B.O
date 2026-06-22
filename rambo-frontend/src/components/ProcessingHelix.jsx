import React, { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

const RING_COUNT = 3;
const RING_RADIUS = 1.85;
const RING_SEGMENTS = 64;

export default function ProcessingHelix({ active = false }) {
  const groupRef = useRef();
  const opacityRef = useRef(0);

  const rings = useMemo(() => {
    return Array.from({ length: RING_COUNT }, (_, i) => {
      const pts = [];
      for (let j = 0; j <= RING_SEGMENTS; j++) {
        const a = (j / RING_SEGMENTS) * Math.PI * 2;
        pts.push(
          Math.cos(a) * RING_RADIUS,
          Math.sin(a * 2 + i * 1.2) * 0.15,
          Math.sin(a) * RING_RADIUS
        );
      }
      const geo = new THREE.BufferGeometry();
      geo.setAttribute("position", new THREE.Float32BufferAttribute(pts, 3));
      const mat = new THREE.LineBasicMaterial({
        color: new THREE.Color("#e8b15a"),
        transparent: true,
        opacity: 0,
        depthWrite: false,
        depthTest: false,
        blending: THREE.AdditiveBlending,
      });
      return { geo, mat, tiltX: (i - 1) * 0.35 };
    });
  }, []);

  useFrame(({ clock }) => {
    const target = active ? 0.25 : 0;
    opacityRef.current += (target - opacityRef.current) * 0.08;
    const t = clock.getElapsedTime();

    rings.forEach((ring, i) => {
      ring.mat.opacity = opacityRef.current;
    });

    if (groupRef.current) {
      groupRef.current.rotation.y = t * 0.6;
      groupRef.current.children.forEach((child, i) => {
        child.rotation.x = rings[i]?.tiltX || 0;
        child.rotation.z = Math.sin(t * 0.8 + i * 2) * 0.1;
      });
    }
  });

  return (
    <group ref={groupRef}>
      {rings.map((ring, i) => (
        <line key={i} geometry={ring.geo} material={ring.mat} renderOrder={2} />
      ))}
    </group>
  );
}

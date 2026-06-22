# R.A.M.B.O MK XVII

**Responsive Autonomous Multi‑Brain Operator**

---

## Overview

R.A.M.B.O MK XVII is a cinematic React + React Three Fiber project that visualizes a breathing red hologram orb and a transparent sci‑fi HUD. It demonstrates custom GLSL shaders, a full‑screen Three.js canvas, and a polished UI with neon glows, ripple effects, and a glitch intro.

---

## Features

- **Full‑screen breathing red hologram orb** (particles + shaders)  
- **Custom GLSL vertex and fragment shaders**  
- **React Three Fiber integration** (Canvas + components)  
- **Transparent HUD** with centered title and subtitle  
- **System stats** with animated bars and floating dock icons  
- **Glitch intro animation** and ripple pulse behind title  
- **Global SF Planetary Orbiter font** integration

---

## Project Structure

src/
└── components/
├── RamboOrb3D.jsx
├── RamboOrbShaders.js
├── SplashScreen.js
└── SplashScreen.css


---

## Components

### RamboOrb3D.jsx
- Generates particle geometry (1600 particles)  
- Builds optional connection lines  
- Uses `ShaderMaterial` with uniforms: `uTime`, `uPixelRatio`, `uBaseSize`, `uRotationSpeed`, `uColor`, `uColorCore`  
- Implements breathing animation via `useFrame`

### RamboOrbShaders.js
- Vertex shader: rotation, wobble, point sizing  
- Fragment shader: soft falloff, core glow, color mixing  
- Line shaders for connection segments

### SplashScreen.js
- Renders `Canvas` behind UI  
- Left panel: System Online, initialization text, transcript  
- Center: PROJECT label, centered title, subtitle  
- Footer: stat panel and dock with SVG icons

### SplashScreen.css
- Global font override to SF Planetary Orbiter  
- Transparent HUD styling  
- Neon glows, ripple animation, glitch intro  
- Responsive layout rules

---

## How to Run

1. Ensure Node.js and npm are installed.  
2. Install dependencies:
```bash
npm install

Start the dev server:
npm start

Notable Code Snippets:
<div className="orb-canvas">
  <Canvas camera={{ position: [0,0,4.2], fov: 45 }} gl={{ antialias: true, alpha: true }}>
    <RamboOrb3D />
  </Canvas>
</div>

Shader Uniform Setup (RamboOrb3D.jsx)
uniforms: {
  uTime: { value: 0 },
  uPixelRatio: { value: Math.min(window.devicePixelRatio, 2) },
  uBaseSize: { value: 4.5 },
  uRotationSpeed: { value: 0.06 },
  uColor: { value: new THREE.Color('#ff2a2a') },
  uColorCore: { value: new THREE.Color('#ff6b6b') },
}

Development Notes
Keep the Canvas inside the React tree and ensure R3F hooks run only inside Canvas.

For bloom/glow, consider adding @react-three/postprocessing Bloom effect.

Tune particle counts and uBaseSize for performance on mobile.

Add fallbacks for devices that do not support custom shaders.
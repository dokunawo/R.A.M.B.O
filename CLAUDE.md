# R.A.M.B.O Orb — Project Context

Splash screen for an AI orchestrator. Phase 1 = a single "living" particle orb with a title. Phase 2 (planned) = the same orb visualizing a multi-agent system it manages.

## Stack

- React + `@react-three/fiber` (R3F) for the 3D scene
- Vanilla `three.js` r128 conventions (custom `THREE.ShaderMaterial`, not drei abstractions)
- `@react-three/postprocessing` for bloom — **not yet installed, you need to run this:**
  ```bash
  npm install @react-three/postprocessing postprocessing
  ```
- Plain CSS (`SplashScreen.css`), no CSS-in-JS

## File map

| File | Job |
|---|---|
| `RamboOrbShaders.js` | All GLSL — particle shader, line shader (shared by rings + spokes), plasma-core shader |
| `RamboOrb3D.jsx` | Scene graph — particle shell, orbit rings, radiating spokes, plasma core, cursor parallax |
| `SplashScreen.js` | DOM/HUD chrome — header, title stack, stat bars, dock, mounts `<Canvas>` |
| `SplashScreen.css` | Dark theme, monospace type, title glow, layout |

## Hard-won lessons — read before touching the shaders

These are bugs that already shipped once. Don't reintroduce them.

1. **Point-size formula is calibration-sensitive.** `gl_PointSize` in `RamboOrbShaders.js` uses `uPerspective / dist`, where `uPerspective` must stay close to the camera's actual `position.z` (currently `4.2`, set as `CAMERA_DISTANCE` in `RamboOrb3D.jsx`). If you change the camera distance, update `CAMERA_DISTANCE` too, or every particle balloons into one solid blurred disc. (This is exactly what happened the first time — a `220.0 / dist` constant with no calibration turned 1600 particles into a giant red blob.)

2. **`THREE.Sprite` is always a flat rectangle unless it has a circular alpha-masked texture or map.** The plasma core is NOT a `Sprite` — it's a `Mesh` + `PlaneGeometry` with a custom shader, manually billboarded each frame via `meshRef.current.quaternion.copy(camera.quaternion)`. If you're tempted to swap it back to a `Sprite` for simplicity, you'll get the "breathing square" bug again unless you also build a circular texture for it.

3. **The dock icons need `width: 100%; height: 100%` on the `svg` selector**, not just on the parent button. Inline SVGs default to their intrinsic size and silently fail to fill a sized button otherwise — they rendered as empty outlined squares before this was added to `SplashScreen.css`.

4. **Title positioning is intentionally outside the grid.** `.orb-title-stack` is centered on the full viewport (`left: 50%; transform: translate(-50%, -50%)`), not inside `.splash-main`'s grid column. If you put title content back inside the left-column grid, it'll drift off the orb's true center again.

## Current state (Phase 1)

- Gold/amber color scheme (`#caa46b` → `#fff4da`), matches the reference VFX still the user is targeting
- ~4000 particles in a shell distribution, 6 tilted orbit rings, 16 radiating spokes, plasma-textured core
- Synced "breathing" animation across all elements (same sine curve, called independently per-component — see `breathe()` in `RamboOrb3D.jsx`)
- Cursor parallax on the dust shell only; the core stays billboard-stable as a deliberate design choice (calm center, reactive shell)
- Center title shows `R.A.M.B.O` only — `MK XVII` was deliberately removed from center copy (top bar still has it)
- Bloom relies on `@react-three/postprocessing` — **confirm this installed and renders before doing further visual tuning**, since none of the glow/halo effect is visible without it

## Open items / Phase 2 direction

Not built yet — flagging so a fresh session doesn't have to rediscover these from scratch:

- **Reduced motion**: `parallax` prop exists on `RamboOrb3D` as an on/off switch, but nothing currently reads `prefers-reduced-motion` to set it. Same for the breathing animation — no kill switch yet.
- **Dock icon set mismatch**: current icons (mic, camera-off, hand-raise) are video-call vocabulary, not orchestrator vocabulary. Rendering bug is fixed; the icon *choices* haven't been revisited.
- **Satellite agent orbs (Phase 2 concept, not started)**: the ring/spoke system is structurally close to a multi-agent visualization. Idea: each managed agent = a small plasma orb riding a point along one of the existing ring paths, with its own `uIntensity`/color driven by that agent's live status (idle/active/error). Proposed shape: `agents: [{ id, status, ringIndex, angleOffset }]` passed into `RamboOrb3D`. Not implemented — needs design pass before building.
- **Core sizing is eyeballed, not computed.** `CORE_SIZE = ORB_RADIUS * 0.78` in `RamboOrb3D.jsx` was tuned by visual feedback against one specific font-size/viewport combo. If title copy length or font sizing changes meaningfully, this likely needs re-tuning by eye — there's no programmatic link between the HTML title's pixel width and the 3D plane's world-unit size.

## Design tokens

```
--accent: #e8b15a       /* primary gold */
--accent-glow: #ffd98a  /* hot highlight */
colorOuter: #caa46b     /* particle/core outer */
colorCore:  #fff4da     /* particle/core hot center */
colorRing:  #d9a857     /* orbit rings */
colorSpoke: #ffe9c2     /* radiating spokes */
```

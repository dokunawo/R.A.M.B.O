# Trillion UI Adaptation — Design Spec

## Overview

Adapt three visual patterns from the Trillion voice-first UI into R.A.M.B.O's existing interface: glass-morphism surfaces, a bottom-center mic button, and polished response cards. Two-tone accent system: gold (#e8b15a) for identity/status, teal (#2DD4A8) for interactive elements.

## 1. Glass-Morphism Surfaces

### What changes

Every panel currently using opaque dark backgrounds (`rgba(8,9,11,0.85)` or similar) gets swapped to frosted glass.

**New shared glass properties:**
```css
background: rgba(14, 15, 19, 0.15);
backdrop-filter: blur(14px);
-webkit-backdrop-filter: blur(14px);
border: 1px solid rgba(255, 255, 255, 0.06);
```

### Affected components and their current backgrounds

| Component | File | Current Background | Selector(s) |
|-----------|------|--------------------|-------------|
| SplashScreen topbar | SplashScreen.css | `rgba(8,9,11,0.85)` | `.splash-topbar` |
| Agent roster panel | SplashScreen.css | opaque dark | `.roster-panel` or equivalent |
| System parameters panel | SplashScreen.css | opaque dark | `.params-panel` or equivalent |
| Command input area | SplashScreen.css | opaque dark | command input container |
| AgentPage topbar | AgentPage.css | `rgba(8,9,11,0.85)` | `.ap-topbar` |
| AgentPage left panel | AgentPage.css | opaque dark | `.ap-left-panel` |
| AgentPage right panel | AgentPage.css | opaque dark | `.ap-right-panel` |
| AgentPage quick-switch bar | AgentPage.css | opaque dark | `.ap-quickswitch` |
| Response branch cards | AgentPage.css | opaque dark | `.ap-response-branch` or equivalent |
| CommandLog | VoiceControls.css | `rgba(8,9,11,0.85)` | `.cmd-log` |
| CommandLog entries | VoiceControls.css | `rgba(14,17,22,0.6)` | `.cmd-log-entry` |
| VoiceControls buttons | VoiceControls.css | `rgba(8,9,11,0.6)` | `.vc-btn` |
| RoundTable panels | RoundTable.css | opaque dark | panel selectors |
| LearningLog panels | LearningLog.css | opaque dark | panel selectors |

### What stays the same

- All text colors (gold `#e8b15a`, white, dim grays)
- All gold borders and accents
- Font family (JetBrains Mono)
- Agent-specific colors in AGENT_META
- Layout positions and sizes — only backgrounds change

### CSS variable approach

Add a shared glass mixin via CSS custom properties in `:root`:
```css
--glass-bg: rgba(14, 15, 19, 0.15);
--glass-blur: blur(14px);
--glass-border: 1px solid rgba(255, 255, 255, 0.06);
```

Each component CSS file references these instead of hardcoded values, keeping future tuning centralized.

## 2. Bottom-Center Mic Button

### Current state

`VoiceControls` renders two small pill-shaped buttons (mic + volume) fixed to bottom-right (`right: 16px; bottom: 16px`). 34px height, gold-bordered.

### New design

**Layout:** Fixed bottom-center bar, transparent background (`pointer-events: none`), centers a single primary mic button. Volume toggle becomes a small 32px secondary button offset to the right of the main button.

**Mic button — idle state:**
- 64x64px circle
- Background: `#16171D`
- Border: `1px solid rgba(255, 255, 255, 0.08)`
- White microphone SVG icon centered (24px)
- `pointer-events: auto` on the button itself

**Mic button — active (listening) state:**
- Border color: `#2DD4A8` (teal)
- Icon swaps to white stop square SVG (16px)
- Box-shadow: `0 0 24px rgba(45, 212, 168, 0.5)`
- Expanding pulse ring via `::after` pseudo-element:
  - `border: 2px solid #2DD4A8`
  - Keyframe: scale 1 → 1.5, opacity 1 → 0, 1.4s infinite
  - Easing: `cubic-bezier(0.16, 1, 0.3, 1)`

**Mic button — processing state:**
- Border color: teal, but pulse ring stops
- Icon: a small spinner or the stop square with reduced opacity
- Indicates command is being processed

**Hint text:**
- Below the button, 11px uppercase
- `rgba(255, 255, 255, 0.4)`, letter-spacing `0.08em`
- Text: `TAP OR SAY 'RAMBO'`
- Hidden when active (listening)

**Volume toggle:**
- 32px circle, positioned 12px to the right of the mic button
- Same glass treatment as other surfaces
- Gold speaker icon, same toggle behavior as current

### Files changed

- `VoiceControls.jsx` — restructure JSX: outer container centered, mic button as primary, volume as secondary
- `VoiceControls.css` — complete restyle of `.voice-controls`, `.vc-btn`; add `.vc-mic-primary`, `.vc-mic-active`, `.vc-pulse-ring`, `.vc-hint`, `.vc-vol-secondary`

### Teal accent scope

Teal (#2DD4A8) is used ONLY on:
- Mic button active border
- Mic button active glow/shadow
- Pulse ring
- Response card top accent bar (see section 3)

Everything else remains gold.

## 3. Response Card Polish

### Current state

Response branch panels on AgentPage connect to the orb via bezier SVG curves. They have opaque dark backgrounds.

### Changes

1. **Glass background** — same `--glass-bg` / `--glass-blur` / `--glass-border` as all other panels
2. **Teal top accent bar** — 2px solid `#2DD4A8` border-top on each response card
3. **Float animation** — gentle vertical bob:
   ```css
   @keyframes responseFloat {
     0%, 100% { transform: translateY(0px); }
     50% { transform: translateY(-6px); }
   }
   ```
   Duration: 4s, easing: `ease-in-out`, infinite loop
4. **Entry animation** — on mount, cards fade in with `rotateX(8deg)` that resolves to `rotateX(0)` over 300ms using `cubic-bezier(0.16, 1, 0.3, 1)`

### What stays the same

- Bezier SVG connectors to orb — unchanged
- Card positioning logic — unchanged
- Card content structure — unchanged
- Minimize/dismiss controls — unchanged

## 4. Shared Easing

Add to `:root`:
```css
--ease-smooth: cubic-bezier(0.16, 1, 0.3, 1);
```

Use on all new transitions and animations for consistency. Don't retroactively change existing animations that already work.

## 5. Scope Boundaries

### Do NOT change
- CosmicOrb.jsx / CosmicOrbShaders.js — no shader or bloom changes
- useVoiceReactivity.js — no voice logic changes
- SplashScreen.js Phase 1 boot sequence logic
- Backend anything
- Agent metadata or colors
- Bloom settings (threshold 0.7, intensity 0.6, radius 0.5, smoothing 0.95)

### Risk areas
- `SplashScreen.js` is ~1250 lines. Changes should be CSS-only where possible. If JSX changes are needed in SplashScreen, keep them minimal.
- `backdrop-filter` performance — may need `will-change: backdrop-filter` or reduced blur radius on mobile. The existing `usePerformanceMode` hook could gate this.
- Some panels may need their `z-index` adjusted so `backdrop-filter` composites correctly against the orb canvas.

## 6. Testing

- Verify at 80% Chrome zoom (Daniel's default)
- Check that orb is visible through all glass panels
- Confirm mic button pulse ring doesn't interfere with other click targets
- Verify voice system still works (singleton pattern, wake word, TTS)
- Check all pages: SplashScreen (Phase 1 + 2), AgentPage, RoundTable, LearningLog

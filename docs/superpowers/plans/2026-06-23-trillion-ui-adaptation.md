# Trillion UI Adaptation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adapt three Trillion UI patterns into R.A.M.B.O — glass-morphism surfaces, a bottom-center mic button with teal pulse ring, and polished floating response cards.

**Architecture:** CSS-first changes across 6 CSS files, one JSX restructure (VoiceControls.jsx). New CSS variables in `:root` centralize glass and teal tokens. No shader, bloom, or voice logic changes.

**Tech Stack:** React 19, CSS3 (backdrop-filter, custom properties, keyframe animations)

## Global Constraints

- Do NOT modify `CosmicOrb.jsx`, `CosmicOrbShaders.js`, or any bloom settings (threshold 0.7, intensity 0.6, radius 0.5, smoothing 0.95)
- Do NOT modify `useVoiceReactivity.js` — voice singleton is load-bearing
- Do NOT modify `SplashScreen.js` JSX — CSS-only changes for that file
- Keep gold `#e8b15a` for all identity/status elements; teal `#2DD4A8` only for mic button active state and response card accent bars
- Test at 80% Chrome zoom
- Use `cubic-bezier(0.16, 1, 0.3, 1)` for all new transitions/animations
- Commit after each task with `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>`

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `SplashScreen.css` | Modify | Add `:root` glass/teal vars, swap panel backgrounds to glass |
| `AgentPage.css` | Modify | Glass backgrounds on panels, teal accent bar + float animation on response cards |
| `RoundTable.css` | Modify | Glass on topbar and agent nodes |
| `LearningLog.css` | Modify | Glass on topbar, info card, list items |
| `VoiceControls.css` | Modify | Complete restyle: centered mic button, pulse ring, hint text |
| `VoiceControls.jsx` | Modify | Restructure JSX: centered layout, primary mic + secondary volume, hint text, convState-driven classes |

---

### Task 1: Add Glass & Teal CSS Variables to `:root`

**Files:**
- Modify: `rambo-frontend/src/components/SplashScreen.css:1-15`

**Interfaces:**
- Produces: CSS variables `--glass-bg`, `--glass-blur`, `--glass-border`, `--teal`, `--teal-glow`, `--ease-smooth` available to all components (SplashScreen.css is imported first and defines `:root`)

- [ ] **Step 1: Add new variables to `:root` block**

In `SplashScreen.css`, add these variables after the existing `--mono` line (line 14):

```css
  --glass-bg: rgba(14, 15, 19, 0.15);
  --glass-blur: blur(14px);
  --glass-border: 1px solid rgba(255, 255, 255, 0.06);
  --teal: #2DD4A8;
  --teal-glow: rgba(45, 212, 168, 0.5);
  --ease-smooth: cubic-bezier(0.16, 1, 0.3, 1);
```

The full `:root` block should read:
```css
:root {
  --bg: #08090b;
  --line: rgba(255, 255, 255, 0.08);
  --line-strong: rgba(255, 255, 255, 0.16);
  --text-hi: #ffffff;
  --text-mid: #d0d0d0;
  --text-dim: #7a7a7a;
  --accent: #e8b15a;
  --accent-glow: #ffd98a;
  --mono: "JetBrains Mono", "Share Tech Mono", monospace;
  --glass-bg: rgba(14, 15, 19, 0.15);
  --glass-blur: blur(14px);
  --glass-border: 1px solid rgba(255, 255, 255, 0.06);
  --teal: #2DD4A8;
  --teal-glow: rgba(45, 212, 168, 0.5);
  --ease-smooth: cubic-bezier(0.16, 1, 0.3, 1);
}
```

- [ ] **Step 2: Verify the app still loads**

Run: `cd rambo-frontend && npm start`

Expected: App loads without CSS errors. No visual change yet — variables are defined but not consumed.

- [ ] **Step 3: Commit**

```bash
git add rambo-frontend/src/components/SplashScreen.css
git commit -m "Add glass-morphism and teal CSS variables to :root"
```

---

### Task 2: Glass-Morphism on SplashScreen Panels

**Files:**
- Modify: `rambo-frontend/src/components/SplashScreen.css:1105-1177` (roster panel, agent panel/params), `1286-1331` (cmd-console), `276-289` (dock), `1786-1796` (branch-panel)

**Interfaces:**
- Consumes: `--glass-bg`, `--glass-blur`, `--glass-border` from Task 1

- [ ] **Step 1: Swap roster panel `.brief-agent-list` background**

Change `.roster-panel .brief-agent-list` (line ~1131) from:
```css
  background: rgba(232, 177, 90, 0.02);
```
to:
```css
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: var(--glass-border);
```

- [ ] **Step 2: Swap agent panel `.brief-params` background**

Change `.agent-panel .brief-params` (line ~1172) from:
```css
  background: rgba(232, 177, 90, 0.02);
```
to:
```css
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: var(--glass-border);
```

- [ ] **Step 3: Swap command feed and input backgrounds**

Change `.cmd-feed` (line ~1301) from:
```css
  background: rgba(8, 9, 11, 0.55);
  backdrop-filter: blur(8px);
```
to:
```css
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: var(--glass-border);
```

Change `.cmd-input-row` (line ~1327) from:
```css
  background: rgba(8, 9, 11, 0.55);
  backdrop-filter: blur(8px);
```
to:
```css
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: var(--glass-border);
```

- [ ] **Step 4: Swap dock background**

Change `.dock` (line ~287) from:
```css
  background: rgba(8, 9, 11, 0.35);
  backdrop-filter: blur(10px);
```
to:
```css
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
```

- [ ] **Step 5: Swap branch-panel background**

Change `.branch-panel` (line ~1793) from:
```css
  background: rgba(10, 11, 14, 0.97);
```
to:
```css
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: var(--glass-border);
```

- [ ] **Step 6: Swap systems-nav background**

Change `.systems-nav` (line ~1637) from:
```css
  background: rgba(232, 177, 90, 0.02);
```
to:
```css
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: var(--glass-border);
```

- [ ] **Step 7: Swap agent-response-body background**

Change `.agent-response-body` (line ~1686) from:
```css
  background: rgba(232, 177, 90, 0.05);
```
to:
```css
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
```

- [ ] **Step 8: Verify visually**

Load the app, navigate to Phase 2. Confirm:
- Agent roster panel is frosted glass — orb visible through it
- System parameters panel is frosted glass
- Command console input and feed are frosted glass
- Dock is frosted glass
- All gold text/borders still render correctly on glass
- No visual artifacts at 80% zoom

- [ ] **Step 9: Commit**

```bash
git add rambo-frontend/src/components/SplashScreen.css
git commit -m "Apply glass-morphism to SplashScreen panels"
```

---

### Task 3: Glass-Morphism on AgentPage Panels

**Files:**
- Modify: `rambo-frontend/src/components/AgentPage.css:37-49` (topbar), `139-148` (panel-frame), `265-278` (branch-panel), `371-385` (quick-switch)

**Interfaces:**
- Consumes: `--glass-bg`, `--glass-blur`, `--glass-border` from Task 1

- [ ] **Step 1: Swap `.ap-topbar` background**

Change `.ap-topbar` (line ~47) from:
```css
  background: rgba(8, 9, 11, 0.85);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid rgba(255,255,255,0.06);
```
to:
```css
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border-bottom: var(--glass-border);
```

- [ ] **Step 2: Swap `.ap-panel-frame` background**

Change `.ap-panel-frame` (line ~140) from:
```css
  border: 1px solid rgba(232, 177, 90, 0.16);
  border-radius: 4px;
  padding: 14px 16px;
  background: rgba(8, 9, 11, 0.65);
  backdrop-filter: blur(10px);
```
to:
```css
  border: var(--glass-border);
  border-radius: 4px;
  padding: 14px 16px;
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
```

- [ ] **Step 3: Swap `.ap-branch-panel` background**

Change `.ap-branch-panel` (line ~273) from:
```css
  background: rgba(10, 11, 14, 0.94);
  backdrop-filter: blur(12px);
  box-shadow: 0 0 30px rgba(232, 177, 90, 0.15);
```
to:
```css
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  box-shadow: 0 0 30px rgba(232, 177, 90, 0.15);
```

- [ ] **Step 4: Swap `.ap-quick-switch` background**

Change `.ap-quick-switch` (line ~382) from:
```css
  background: rgba(8, 9, 11, 0.85);
  backdrop-filter: blur(10px);
  border-top: 1px solid rgba(255, 255, 255, 0.06);
```
to:
```css
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border-top: var(--glass-border);
```

- [ ] **Step 5: Swap `.ap-status-floating` background**

Change `.ap-status-floating` (line ~118) from:
```css
  background: rgba(8, 9, 11, 0.7);
  backdrop-filter: blur(8px);
```
to:
```css
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
```

- [ ] **Step 6: Verify visually**

Navigate to any agent page. Confirm:
- Topbar is frosted glass
- Left and right panels are frosted glass — orb visible through them
- Quick-switch bar at bottom is frosted glass
- Response branch panels are frosted glass
- Agent-colored borders and text still render correctly

- [ ] **Step 7: Commit**

```bash
git add rambo-frontend/src/components/AgentPage.css
git commit -m "Apply glass-morphism to AgentPage panels"
```

---

### Task 4: Glass-Morphism on RoundTable and LearningLog

**Files:**
- Modify: `rambo-frontend/src/components/RoundTable.css:35-44` (topbar), `129-140` (agent nodes)
- Modify: `rambo-frontend/src/components/LearningLog.css:36-47` (topbar), `118-131` (info card), `183-188` (list items)

**Interfaces:**
- Consumes: `--glass-bg`, `--glass-blur`, `--glass-border` from Task 1

- [ ] **Step 1: Swap `.rt-topbar` background**

Change `.rt-topbar` (line ~42) from:
```css
  background: rgba(8, 9, 11, 0.7);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid rgba(255,255,255,0.06);
```
to:
```css
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border-bottom: var(--glass-border);
```

- [ ] **Step 2: Swap `.rt-agent-node` background**

Change `.rt-agent-node` (line ~132) from:
```css
  background: rgba(8, 9, 11, 0.85);
```
to:
```css
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
```

- [ ] **Step 3: Swap `.ll-topbar` background**

Change `.ll-topbar` (line ~44) from:
```css
  background: rgba(8, 9, 11, 0.92);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid rgba(255,255,255,0.06);
```
to:
```css
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border-bottom: var(--glass-border);
```

- [ ] **Step 4: Swap `.ll-info-card` background**

Change `.ll-info-card` (line ~128) from:
```css
  background: rgba(14, 17, 22, 0.9);
```
to:
```css
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
```

- [ ] **Step 5: Swap `.ll-item` background**

Change `.ll-item` (line ~185) from:
```css
  background: rgba(14, 17, 22, 0.5);
```
to:
```css
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
```

- [ ] **Step 6: Verify visually**

Navigate to Round Table and Learning Log pages. Confirm:
- Topbars are frosted glass
- Agent nodes on Round Table are frosted glass circles
- Learning Log cards and info card are frosted glass
- Orb visible through all panels

- [ ] **Step 7: Commit**

```bash
git add rambo-frontend/src/components/RoundTable.css rambo-frontend/src/components/LearningLog.css
git commit -m "Apply glass-morphism to RoundTable and LearningLog"
```

---

### Task 5: Glass-Morphism on VoiceControls (CommandLog)

**Files:**
- Modify: `rambo-frontend/src/components/VoiceControls.css:41-88` (cmd-log, cmd-log-entry)

**Interfaces:**
- Consumes: `--glass-bg`, `--glass-blur`, `--glass-border` from Task 1

- [ ] **Step 1: Swap `.cmd-log` background**

Change `.cmd-log` (line ~50) from:
```css
  background: rgba(8, 9, 11, 0.85);
  border: 1px solid rgba(232, 177, 90, 0.15);
  border-radius: 4px;
  backdrop-filter: blur(10px);
```
to:
```css
  background: var(--glass-bg);
  border: var(--glass-border);
  border-radius: 4px;
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
```

- [ ] **Step 2: Swap `.cmd-log-entry` background**

Change `.cmd-log-entry` (line ~84) from:
```css
  background: rgba(14, 17, 22, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.04);
```
to:
```css
  background: rgba(14, 15, 19, 0.25);
  border: var(--glass-border);
```

- [ ] **Step 3: Verify visually**

Navigate to LearningLog or RoundTable where CommandLog is used. Issue a voice command or type one. Confirm:
- Command log container is frosted glass
- Individual entries have subtle glass treatment
- Text is still readable

- [ ] **Step 4: Commit**

```bash
git add rambo-frontend/src/components/VoiceControls.css
git commit -m "Apply glass-morphism to CommandLog"
```

---

### Task 6: Bottom-Center Mic Button — JSX Restructure

**Files:**
- Modify: `rambo-frontend/src/components/VoiceControls.jsx:70-89`

**Interfaces:**
- Consumes: `micActive`, `toggleMic`, `convState` props (unchanged)
- Produces: New JSX structure with classes `.vc-bar`, `.vc-mic-primary`, `.vc-mic-active`, `.vc-vol-secondary`, `.vc-hint` (styled in Task 7)

- [ ] **Step 1: Rewrite the VoiceControls component JSX**

Replace the `VoiceControls` function (lines 70-89) with:

```jsx
export function VoiceControls({ micActive, toggleMic, convState }) {
  const [muted, setMutedState] = useState(isMuted());
  const toggleVolume = () => {
    resumeAudio();
    setMutedState(setMuted(!muted));
  };

  const isListening = convState === CONV_STATES.LISTENING || convState === CONV_STATES.WAKE_HEARD;
  const isProcessing = convState === CONV_STATES.PROCESSING;
  const isActive = micActive && (isListening || isProcessing);

  return (
    <div className="vc-bar">
      <div className="vc-bar-center">
        <button
          className={`vc-mic-primary${isActive ? " vc-mic-active" : ""}${isProcessing ? " vc-mic-processing" : ""}`}
          type="button"
          onClick={toggleMic}
          title={micActive ? 'Mic active — say "Rambo" to command' : "Enable mic"}
        >
          {isActive ? (
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <rect x="3" y="3" width="10" height="10" rx="1.5" fill="white"/>
            </svg>
          ) : (
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="9" y="2" width="6" height="11" rx="3"/>
              <path d="M5 10a7 7 0 0 0 14 0"/>
              <line x1="12" y1="19" x2="12" y2="22"/>
            </svg>
          )}
        </button>
        <button className="vc-vol-secondary" type="button" onClick={toggleVolume}
          title={muted ? "Sound off — click to enable" : "Sound on"}>
          {muted ? "🔇" : "🔊"}
        </button>
      </div>
      {!isActive && (
        <span className="vc-hint">TAP OR SAY &lsquo;RAMBO&rsquo;</span>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Add CONV_STATES import if not already present**

Check line 2 — `CONV_STATES` is already imported: `import { useVoiceReactivity, CONV_STATES } from "./useVoiceReactivity";`. No change needed.

- [ ] **Step 3: Verify the app compiles**

Run: `cd rambo-frontend && npm start`

Expected: App compiles. The mic button will look broken until Task 7 adds the CSS — that's expected.

- [ ] **Step 4: Commit**

```bash
git add rambo-frontend/src/components/VoiceControls.jsx
git commit -m "Restructure VoiceControls JSX for bottom-center mic button"
```

---

### Task 7: Bottom-Center Mic Button — CSS

**Files:**
- Modify: `rambo-frontend/src/components/VoiceControls.css:1-38` (replace `.voice-controls` and `.vc-btn` blocks)

**Interfaces:**
- Consumes: Classes from Task 6 JSX (`.vc-bar`, `.vc-bar-center`, `.vc-mic-primary`, `.vc-mic-active`, `.vc-mic-processing`, `.vc-vol-secondary`, `.vc-hint`)
- Consumes: `--teal`, `--teal-glow`, `--ease-smooth`, `--glass-bg`, `--glass-blur`, `--glass-border` from Task 1

- [ ] **Step 1: Replace the voice-controls and vc-btn CSS blocks**

Replace lines 1-38 (`.voice-controls` through `.vc-state`) with:

```css
/* ---- Bottom-Center Mic Bar ---- */
.vc-bar {
  position: fixed;
  bottom: 24px;
  left: 0;
  right: 0;
  z-index: 60;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  pointer-events: none;
}

.vc-bar-center {
  display: flex;
  align-items: center;
  gap: 12px;
}

.vc-mic-primary {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: #16171D;
  color: white;
  cursor: pointer;
  display: grid;
  place-items: center;
  pointer-events: auto;
  transition: border-color 0.2s var(--ease-smooth),
              box-shadow 0.2s var(--ease-smooth),
              background 0.2s var(--ease-smooth);
  position: relative;
}

.vc-mic-primary:hover {
  border-color: rgba(255, 255, 255, 0.2);
  box-shadow: 0 0 16px rgba(255, 255, 255, 0.1);
}

/* Active (listening) state — teal */
.vc-mic-active {
  border-color: var(--teal);
  box-shadow: 0 0 24px var(--teal-glow);
}

.vc-mic-active:hover {
  border-color: var(--teal);
  box-shadow: 0 0 32px var(--teal-glow);
}

/* Pulse ring on active */
.vc-mic-active::after {
  content: '';
  position: absolute;
  inset: -4px;
  border-radius: 50%;
  border: 2px solid var(--teal);
  animation: vcPulseRing 1.4s var(--ease-smooth) infinite;
  pointer-events: none;
}

@keyframes vcPulseRing {
  0% {
    transform: scale(1);
    opacity: 1;
  }
  100% {
    transform: scale(1.5);
    opacity: 0;
  }
}

/* Processing state — teal border, no pulse */
.vc-mic-processing {
  border-color: var(--teal);
  box-shadow: 0 0 16px var(--teal-glow);
}
.vc-mic-processing::after {
  display: none;
}

/* Volume toggle — small secondary button */
.vc-vol-secondary {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: var(--glass-border);
  color: var(--accent, #e8b15a);
  font-size: 14px;
  cursor: pointer;
  display: grid;
  place-items: center;
  pointer-events: auto;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.vc-vol-secondary:hover {
  border-color: var(--accent, #e8b15a);
  box-shadow: 0 0 10px rgba(232, 177, 90, 0.3);
}

/* Hint text below */
.vc-hint {
  font-family: var(--mono, "JetBrains Mono", monospace);
  font-size: 11px;
  letter-spacing: 0.08em;
  color: rgba(255, 255, 255, 0.4);
  text-transform: uppercase;
  pointer-events: none;
}

@media (prefers-reduced-motion: reduce) {
  .vc-mic-active::after {
    animation: none;
    display: none;
  }
}
```

- [ ] **Step 2: Also update SplashScreen.css mic/sound toggle styles**

The SplashScreen has its own `.mic-toggle` and `.sound-toggle` styles (lines 1428-1484) that render separate mic/sound buttons. These need to be hidden since VoiceControls now provides the unified mic button.

Add at the end of `.mic-toggle` block:
```css
.mic-toggle,
.sound-toggle {
  display: none;
}
```

Wait — check if SplashScreen renders its own mic buttons separately from VoiceControls. Let me verify before this step.

Read `SplashScreen.js` to see if it uses `VoiceControls` component or has its own buttons.

- [ ] **Step 3: Verify visually**

Load the app. Confirm:
- 64px dark circle mic button centered at bottom of viewport
- White mic SVG icon visible
- Small volume button to the right of mic button with glass treatment
- "TAP OR SAY 'RAMBO'" hint text below
- Click mic — teal border appears, teal glow, pulsing ring animation
- Ring expands and fades smoothly with `cubic-bezier(0.16, 1, 0.3, 1)` easing
- Icon swaps to white stop square when active
- Hint text disappears when active
- Click again — returns to idle state
- Test at 80% Chrome zoom

- [ ] **Step 4: Commit**

```bash
git add rambo-frontend/src/components/VoiceControls.css
git commit -m "Style bottom-center mic button with teal pulse ring"
```

---

### Task 8: Response Card Polish — Teal Accent Bar + Float Animation

**Files:**
- Modify: `rambo-frontend/src/components/AgentPage.css:254-344` (branch panel styles)
- Modify: `rambo-frontend/src/components/SplashScreen.css:1770-1842` (branch panel styles)

**Interfaces:**
- Consumes: `--teal`, `--ease-smooth` from Task 1
- Consumes: Glass background already applied in Task 3 (AgentPage) and Task 2 (SplashScreen)

- [ ] **Step 1: Add teal accent bar and float animation to AgentPage response cards**

Add to `.ap-branch-panel` (after existing properties in AgentPage.css):
```css
  border-top: 2px solid var(--teal);
```

Add these new rules after the `.ap-branch-panel` block:
```css
/* Float animation for response cards */
@keyframes apResponseFloat {
  0%, 100% { transform: translateY(0px); }
  50% { transform: translateY(-6px); }
}

.ap-branch-panel {
  animation: apBranchPop 0.3s var(--ease-smooth), apResponseFloat 4s ease-in-out 0.3s infinite;
}
```

Wait — there's already an `animation` property on `.ap-branch-panel`. The entry animation `apBranchPop` needs to complete before the float starts. Use `animation` shorthand with both:

Replace the existing `animation` line in `.ap-branch-panel`:
```css
  animation: apBranchPop 0.3s var(--ease-smooth, ease);
```
with:
```css
  border-top: 2px solid var(--teal);
  animation: apBranchPop 0.3s var(--ease-smooth, ease) forwards, apResponseFloat 4s ease-in-out 0.3s infinite;
```

Add the float keyframe after the existing `apBranchPop` keyframe:
```css
@keyframes apResponseFloat {
  0%, 100% { transform: translateY(0px); }
  50% { transform: translateY(-6px); }
}
```

- [ ] **Step 2: Add teal accent bar and float animation to SplashScreen response cards**

Add `border-top: 2px solid var(--teal);` to `.branch-panel` in SplashScreen.css.

Replace the existing `animation` line in `.branch-panel`:
```css
  animation: resultPop 0.22s ease;
```
with:
```css
  border-top: 2px solid var(--teal);
  animation: resultPop 0.22s var(--ease-smooth, ease) forwards, responseFloat 4s ease-in-out 0.22s infinite;
```

Add the float keyframe after `resultPop`:
```css
@keyframes responseFloat {
  0%, 100% { transform: translateY(0px); }
  50% { transform: translateY(-6px); }
}
```

- [ ] **Step 3: Add reduced-motion override for float**

Add to the `@media (prefers-reduced-motion: reduce)` block in AgentPage.css (if one exists, otherwise create one):
```css
@media (prefers-reduced-motion: reduce) {
  .ap-branch-panel {
    animation: none !important;
  }
}
```

Add to SplashScreen.css reduced-motion block:
```css
  .branch-panel {
    animation: none !important;
  }
```

- [ ] **Step 4: Verify visually**

Issue a command on an agent page. Confirm:
- Response card has a 2px teal bar at the top
- Card gently bobs up and down (±6px, 4s cycle)
- Entry animation still plays (pop-in) before float starts
- Float animation doesn't interfere with dragging
- Bezier SVG connectors still render correctly
- Test same on Phase 2 (SplashScreen)

- [ ] **Step 5: Commit**

```bash
git add rambo-frontend/src/components/AgentPage.css rambo-frontend/src/components/SplashScreen.css
git commit -m "Add teal accent bar and float animation to response cards"
```

---

### Task 9: Handle SplashScreen's Own Mic/Sound Buttons

**Files:**
- Modify: `rambo-frontend/src/components/SplashScreen.css:1428-1484` (mic-toggle, sound-toggle)

**Interfaces:**
- Depends on: Task 7 (new VoiceControls is the sole mic UI)

SplashScreen.js renders its own `.mic-toggle` and `.sound-toggle` buttons separately from the `VoiceControls` component. Since VoiceControls now provides a unified bottom-center mic button that appears on all pages, we need to check whether these duplicate or whether VoiceControls only renders on sub-pages.

- [ ] **Step 1: Check what SplashScreen.js renders for mic controls**

Read `SplashScreen.js` and search for `mic-toggle`, `sound-toggle`, `VoiceControls`. Determine:
- Does SplashScreen import and use `VoiceControls`?
- Or does it render its own mic/sound buttons?

- [ ] **Step 2: Resolve duplication**

If SplashScreen renders its own mic buttons AND also mounts VoiceControls, hide the SplashScreen-specific ones by adding to SplashScreen.css:
```css
.mic-toggle,
.sound-toggle {
  display: none;
}
```

If SplashScreen does NOT use VoiceControls at all, it has its own voice system — leave its buttons alone but apply glass-morphism to `.mic-toggle` and `.sound-toggle`:
```css
.mic-toggle,
.sound-toggle {
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: var(--glass-border);
}
```

- [ ] **Step 3: Verify**

Load Phase 2. Confirm there's only one mic button visible (bottom center) and no duplicate controls.

- [ ] **Step 4: Commit**

```bash
git add rambo-frontend/src/components/SplashScreen.css
git commit -m "Resolve mic button duplication between SplashScreen and VoiceControls"
```

---

### Task 10: Final Visual QA Pass

**Files:** None to modify (unless issues found)

- [ ] **Step 1: Full-app walkthrough at 80% Chrome zoom**

Navigate through every page in order and check:
1. **Phase 1 (boot sequence)** — orb renders, boot text visible, no glass artifacts
2. **Phase 2 (console)** — roster panel glass, params panel glass, command console glass, dock glass, orb visible through all panels
3. **Agent page (any agent)** — topbar glass, left/right panels glass, quick-switch bar glass
4. **Issue a voice command on agent page** — response card appears with teal top bar, floats gently, glass background
5. **Round Table** — topbar glass, agent nodes glass circles, orb visible
6. **Learning Log** — topbar glass, info card glass, list items glass
7. **Mic button on every page** — 64px centered, idle=dark, active=teal pulse ring, volume button visible

- [ ] **Step 2: Check z-index compositing**

Confirm `backdrop-filter` works on all panels — if any panel appears fully transparent or fully opaque, its z-index relative to the orb canvas may need adjustment. The orb canvas is at `z-index: 0`, panels should be at `z-index: 2+`.

- [ ] **Step 3: Fix any issues found**

If issues are found, fix them and commit with a descriptive message.

- [ ] **Step 4: Final commit if any fixes were needed**

```bash
git add -A
git commit -m "Fix visual issues from Trillion UI adaptation QA pass"
```

# CMC poster assets (`/cmc/...`)

These files are served **same-origin** by the frontend, so the Daily Edge poster
(`/card/:market`) can layer them in AND the "Download PNG" export stays clean (no
canvas tainting). Drop replacements here with the **exact same filename** and they
plug straight in — no code change needed.

| File | Used as | Status | How to (re)make |
|------|---------|--------|-----------------|
| `smoke-bg.png` | full-bleed background plate | generated (Pillow) | overwrite with a ChatGPT smoke plate for higher-end art |
| `gold-dust.png` | floating gold-dust overlay | generated (Pillow) | optional to replace |
| `grunge.png` | grain/scratch overlay | generated (Pillow) | optional to replace |
| `cmc-logo.png` | top brand logo | **empty — drop yours here** | ChatGPT, transparent PNG, ~1024², crown + CMC + wordmark |

Until `cmc-logo.png` exists, the poster falls back to the CSS gold-foil "CMC"
wordmark automatically.

## ChatGPT prompts (path A — best art)

**Logo** (`cmc-logo.png`): "A logo on a transparent background. The letters CMC in a
bold gold metallic brushstroke/graffiti style, a gold crown above, and CHANCES MAKE
CHAMPIONS in small spaced letters beneath. Gold #d6a21e with white highlights, subtle
glow, premium sports-betting brand. Transparent PNG, 1024×1024."

**Smoke plate** (`smoke-bg.png`): "Full-bleed texture, 1536×1024, pure black with gold
and amber smoke drifting from the corners, faint gold dust, soft vignette. NO text, NO
logos, NO boxes — only atmospheric black-and-gold smoke."

Rules: no text and no tile/box shapes baked into the art (the market title and the 3
pick cards are rendered live in code on top). Regenerate the procedural set anytime:
`CMC_OUT=rambo-frontend/public/cmc python scratchpad/gen_textures.py`.

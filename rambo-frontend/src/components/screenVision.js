// screenVision.js — on-demand screen capture for R.A.M.B.O's "look at my screen"
// ability. The backend runs in a Linux container and can't see the host screen,
// so capture happens here in the browser (same place the mic works).
//
// Model: a persistent share session. The user flips the SCREEN toggle once and
// picks a surface (browser security mandates the picker — no silent capture);
// we hold that MediaStream alive so each later "look" grabs a frame instantly
// with no re-prompt. captureFrame() downscales to a JPEG to keep vision cost low.

let stream = null;     // the live MediaStream from getDisplayMedia
let videoEl = null;    // hidden <video> playing the stream (frame source)
const listeners = new Set(); // state-change subscribers (for the toggle UI)

const MAX_EDGE = 1280;      // downscale longest edge → ~1k vision tokens
const JPEG_QUALITY = 0.7;

function notify() {
  for (const fn of listeners) { try { fn(isSharing()); } catch { /* ignore */ } }
}

export function onShareChange(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function isSharing() {
  return !!(stream && stream.active);
}

function teardown() {
  if (stream) {
    for (const t of stream.getTracks()) { try { t.stop(); } catch { /* ignore */ } }
  }
  stream = null;
  if (videoEl) { try { videoEl.srcObject = null; } catch { /* ignore */ } }
}

export async function startShare() {
  if (isSharing()) return true;
  if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {
    throw new Error("Screen capture isn't supported in this browser.");
  }
  // Hint the whole monitor; the browser still lets the user choose.
  stream = await navigator.mediaDevices.getDisplayMedia({
    video: { displaySurface: "monitor" },
    audio: false,
  });

  if (!videoEl) {
    videoEl = document.createElement("video");
    videoEl.muted = true;
    videoEl.playsInline = true;
    videoEl.style.cssText = "position:fixed;left:-9999px;top:-9999px;width:1px;height:1px;";
    document.body.appendChild(videoEl);
  }
  videoEl.srcObject = stream;
  try { await videoEl.play(); } catch { /* autoplay of a muted video is allowed */ }

  // User clicked the browser's own "Stop sharing" → reset our state.
  const track = stream.getVideoTracks()[0];
  if (track) track.addEventListener("ended", () => { teardown(); notify(); });

  notify();
  return true;
}

export function stopShare() {
  if (!isSharing()) return;
  teardown();
  notify();
}

// Grab one frame from the live stream as a base64 JPEG (no data: prefix).
// Returns null if not sharing or the video has no dimensions yet.
export function captureFrame() {
  if (!isSharing() || !videoEl) return null;
  const vw = videoEl.videoWidth, vh = videoEl.videoHeight;
  if (!vw || !vh) return null;

  const scale = Math.min(1, MAX_EDGE / Math.max(vw, vh));
  const w = Math.max(1, Math.round(vw * scale));
  const h = Math.max(1, Math.round(vh * scale));

  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(videoEl, 0, 0, w, h);

  const dataUrl = canvas.toDataURL("image/jpeg", JPEG_QUALITY);
  const comma = dataUrl.indexOf(",");
  return comma >= 0 ? dataUrl.slice(comma + 1) : null;
}

// Does this command look like it's asking about the screen? Gates capture so
// only screen-directed requests pay for a vision call.
const SCREEN_INTENT = /\b(screen|on (?:my|the) screen|this (?:error|page|code|window)|looking at|look at this|read this|see this|what(?:'s| is) this|on screen)\b/i;
export function isScreenIntent(text) {
  return SCREEN_INTENT.test(text || "");
}

// Returns a base64 frame to attach to this command, or null. Only captures when
// a share is active AND the command reads as screen-directed — so plain
// commands never incur a vision call.
export function frameForGoal(goal) {
  if (!isSharing() || !isScreenIntent(goal)) return null;
  return captureFrame();
}

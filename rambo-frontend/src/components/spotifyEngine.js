// spotifyEngine.js — singleton Spotify Web Playback SDK controller.
//
// One player instance lives at module scope so music keeps playing as you move
// between the Command Center and the agent screens (each widget just subscribes
// to this shared state). The backend holds the OAuth tokens; this only ever sees
// short-lived access tokens fetched from /spotify/token.

const API = "http://localhost:8000";

let player = null;
let deviceId = null;
let sdkLoading = false;
let initStarted = false;

// Music (Spotify player) volume 0..1, persisted so the Settings slider sticks
// across reloads and applies as soon as the player connects.
let musicVol = (() => {
  try {
    const v = parseFloat(localStorage.getItem("rambo-music-volume"));
    return v >= 0 && v <= 1 ? v : 0.6;
  } catch { return 0.6; }
})();

let state = {
  configured: false,   // SPOTIFY_CLIENT_ID/SECRET present on the backend
  connected: false,    // OAuth completed
  needsReconnect: false, // token missing a now-required scope → reconnect to fix
  ready: false,        // the R.A.M.B.O device is registered & active
  paused: true,
  shuffle: false,
  track: null, artist: null, album: null, art: null,
  position: 0, duration: 0,
  error: null,         // e.g. "premium_required"
};

const listeners = new Set();
const getState = () => ({ ...state });
const emit = () => { for (const fn of listeners) { try { fn(getState()); } catch { /* ignore */ } } };

export function subscribe(fn) {
  listeners.add(fn);
  fn(getState());
  return () => listeners.delete(fn);
}
export { getState };
export const getDeviceId = () => deviceId;

async function fetchStatus() {
  try {
    const r = await fetch(`${API}/spotify/status`);
    if (r.ok) {
      const j = await r.json();
      state.configured = !!j.configured;
      state.connected = !!j.connected;
      state.needsReconnect = !!j.needs_reconnect;
      emit();
      return j;
    }
  } catch { /* offline */ }
  return null;
}

async function getToken() {
  try {
    const r = await fetch(`${API}/spotify/token`);
    const j = await r.json().catch(() => ({}));
    return j.access_token || null;
  } catch { return null; }
}

function loadSDK() {
  return new Promise((resolve, reject) => {
    if (window.Spotify) { resolve(); return; }
    if (sdkLoading) {
      const i = setInterval(() => { if (window.Spotify) { clearInterval(i); resolve(); } }, 150);
      return;
    }
    sdkLoading = true;
    window.onSpotifyWebPlaybackSDKReady = () => resolve();
    const s = document.createElement("script");
    s.src = "https://sdk.scdn.co/spotify-player.js";
    s.async = true;
    s.onerror = reject;
    document.body.appendChild(s);
  });
}

// Idempotent: safe to call from every widget mount. Only the first call wires up.
export async function init() {
  await fetchStatus();
  if (!state.connected || initStarted) return;
  initStarted = true;
  try {
    await loadSDK();
  } catch { initStarted = false; return; }

  player = new window.Spotify.Player({
    name: "R.A.M.B.O",
    getOAuthToken: (cb) => { getToken().then((t) => { if (t) cb(t); }); },
    volume: musicVol,
  });

  player.addListener("ready", ({ device_id }) => {
    deviceId = device_id;
    state.ready = true;
    state.error = null;
    try { player.setVolume(musicVol); } catch { /* ignore */ }
    emit();
    // Register the device so backend voice commands ("play X", "next song") can
    // target this player even before anything is playing.
    fetch(`${API}/spotify/device`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_id }),
    }).catch(() => { /* best-effort */ });
  });
  player.addListener("not_ready", () => { state.ready = false; emit(); });
  player.addListener("player_state_changed", (s) => {
    if (!s) return;
    const t = s.track_window && s.track_window.current_track;
    state.paused = s.paused;
    state.shuffle = !!s.shuffle;
    state.position = s.position;
    state.duration = s.duration;
    state.track = t ? t.name : null;
    state.artist = t ? (t.artists || []).map((a) => a.name).join(", ") : null;
    state.album = t && t.album ? t.album.name : null;
    state.art = t && t.album && t.album.images && t.album.images[0] ? t.album.images[0].url : null;
    emit();
    // Feed the OS media overlay so the album/track shows on hardware media keys.
    if ("mediaSession" in navigator) {
      try {
        if (t) {
          navigator.mediaSession.metadata = new window.MediaMetadata({
            title: t.name,
            artist: (t.artists || []).map((a) => a.name).join(", "),
            album: t.album ? t.album.name : "",
            artwork: ((t.album && t.album.images) || []).map((im) => ({ src: im.url })),
          });
        }
        navigator.mediaSession.playbackState = s.paused ? "paused" : "playing";
      } catch { /* ignore */ }
    }
  });
  player.addListener("initialization_error", ({ message }) => { state.error = message; emit(); });
  player.addListener("authentication_error", ({ message }) => { state.error = message; emit(); });
  player.addListener("account_error", () => { state.error = "premium_required"; emit(); });

  await player.connect();
  setupMediaSession();
}

// Route hardware media keys (play/pause/next/prev) to the R.A.M.B.O player.
function setupMediaSession() {
  if (!("mediaSession" in navigator)) return;
  try {
    navigator.mediaSession.setActionHandler("play", () => resume());
    navigator.mediaSession.setActionHandler("pause", () => pause());
    navigator.mediaSession.setActionHandler("previoustrack", () => prevTrack());
    navigator.mediaSession.setActionHandler("nexttrack", () => nextTrack());
    navigator.mediaSession.setActionHandler("stop", () => pause());
  } catch { /* some keys unsupported on this browser */ }
}

// ── Ducking: drop the music volume while R.A.M.B.O is listening or speaking so
// the mic doesn't capture the song and you can hear R.A.M.B.O over it. ─────────
let preDuckVolume = musicVol;
let ducked = false;
export async function setVoiceDuck(on) {
  if (!player) return;
  try {
    if (on && !ducked) {
      ducked = true;
      const v = await player.getVolume();
      preDuckVolume = v > 0.05 ? v : musicVol;
      await player.setVolume(0.1);
    } else if (!on && ducked) {
      ducked = false;
      await player.setVolume(preDuckVolume);
    }
  } catch { /* ignore */ }
}

// Set the Spotify music volume from a 0-100 percentage (the Spotify widget's
// slider). Persists, and if the player is currently ducked (RAMBO speaking/
// listening) updates the level it will restore to rather than fighting the duck.
export async function setMusicVolume(pct) {
  const v01 = Math.max(0, Math.min(1, (pct || 0) / 100));
  musicVol = v01;
  try { localStorage.setItem("rambo-music-volume", String(v01)); } catch { /* ignore */ }
  preDuckVolume = v01;
  if (player && !ducked) {
    try { await player.setVolume(v01); } catch { /* ignore */ }
  }
}

export function getMusicVolume() { return Math.round(musicVol * 100); }
export function isMusicMuted() { return musicVol <= 0; }

// Quick mute/unmute for the music. Remembers the level so unmute restores it.
let preMuteMusic = 0.6;
export async function toggleMusicMute() {
  if (musicVol > 0) {
    preMuteMusic = musicVol;
    await setMusicVolume(0);
    return 0;
  }
  const restore = Math.round((preMuteMusic > 0 ? preMuteMusic : 0.6) * 100);
  await setMusicVolume(restore);
  return restore;
}

// Open the OAuth popup, poll until connected, then bring the player up.
export function connectSpotify() {
  window.open(`${API}/spotify/login`, "spotify_auth", "width=480,height=760");
  const start = Date.now();
  const poll = setInterval(async () => {
    const j = await fetchStatus();
    if (j && j.connected) { clearInterval(poll); init(); }
    else if (Date.now() - start > 120000) clearInterval(poll);
  }, 1500);
}

export async function disconnect() {
  try { await fetch(`${API}/spotify/disconnect`, { method: "POST" }); } catch { /* ignore */ }
  try { if (player) await player.disconnect(); } catch { /* ignore */ }
  player = null; deviceId = null; initStarted = false;
  state = { ...state, connected: false, ready: false, paused: true, track: null, artist: null, art: null };
  emit();
}

// ── Controls (via the SDK — it owns this player's queue) ─────────────
// The SDK methods drive the R.A.M.B.O device's own playback directly, so they
// advance reliably (incl. Liked Songs / search queues) and honor shuffle. We
// keep playback ON this device (see resolve_device) so these always apply.
// Explicit resume/pause — more reliable than the SDK's togglePlay(), whose
// internal state desyncs when playback was started via the backend Web API (the
// cause of "next/prev work but play/pause does nothing"). Each also asserts the
// OS playbackState so Chrome keeps claiming the hardware play/pause media key,
// and falls back to the backend Web API if the SDK call doesn't take.
function setPlaybackState(s) {
  if ("mediaSession" in navigator) { try { navigator.mediaSession.playbackState = s; } catch { /* ignore */ } }
}
async function _control(action) {  // action: "play" | "pause"
  if (player) {
    try { action === "play" ? await player.resume() : await player.pause(); return; }
    catch { /* fall through to backend */ }
  }
  try {
    await fetch(`${API}/spotify/${action}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_id: deviceId }),
    });
  } catch { /* ignore */ }
}
export async function resume() { setPlaybackState("playing"); return _control("play"); }
export async function pause() { setPlaybackState("paused"); return _control("pause"); }
export async function togglePlay() { return state.paused ? resume() : pause(); }
export async function nextTrack() { if (player) await player.nextTrack(); }
export async function prevTrack() { if (player) await player.previousTrack(); }
export async function seek(ms) { if (player) await player.seek(ms); }

// Start a playlist/track on the R.A.M.B.O device (used by search/playlist clicks).
export async function playUri({ context_uri, uris, offset } = {}) {
  try {
    await fetch(`${API}/spotify/play`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_id: deviceId, context_uri, uris, offset }),
    });
  } catch { /* ignore */ }
}

export async function search(q) {
  try {
    const r = await fetch(`${API}/spotify/search?q=${encodeURIComponent(q)}`);
    return r.ok ? r.json() : {};
  } catch { return {}; }
}

export async function getPlaylists() {
  try {
    const r = await fetch(`${API}/spotify/playlists`);
    return r.ok ? r.json() : {};
  } catch { return {}; }
}

export async function getPlaylistTracks(id) {
  try {
    const r = await fetch(`${API}/spotify/playlist-tracks?playlist_id=${encodeURIComponent(id)}`);
    return r.ok ? r.json() : {};
  } catch { return {}; }
}

export async function getLiked() {
  try {
    const r = await fetch(`${API}/spotify/liked`);
    return r.ok ? r.json() : {};
  } catch { return {}; }
}

export async function playLiked() {
  try {
    await fetch(`${API}/spotify/play-liked`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_id: deviceId }),
    });
  } catch { /* ignore */ }
}

export async function toggleShuffle() {
  const next = !state.shuffle;
  state.shuffle = next;  // optimistic; player_state_changed confirms
  emit();
  try {
    await fetch(`${API}/spotify/shuffle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ state: next, device_id: deviceId }),
    });
  } catch { /* ignore */ }
}

// Re-run OAuth (e.g. to grant a newly-added scope like Liked Songs).
export async function reconnect() {
  await disconnect();
  connectSpotify();
}

import React, { useState, useEffect, useRef, useCallback } from "react";
import * as spotify from "./spotifyEngine";
import "./SpotifyWidget.css";

function fmt(ms) {
  if (!ms || ms < 0) ms = 0;
  const s = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function useSpotifyState() {
  const [state, setState] = useState(spotify.getState());
  useEffect(() => {
    const unsub = spotify.subscribe(setState);
    spotify.init();
    return unsub;
  }, []);
  return state;
}

function useProgress(state) {
  const [pos, setPos] = useState(state.position);
  const anchor = useRef({ pos: state.position, at: Date.now(), paused: state.paused });
  useEffect(() => {
    anchor.current = { pos: state.position, at: Date.now(), paused: state.paused };
    setPos(state.position);
  }, [state.position, state.paused, state.track]);
  useEffect(() => {
    const id = setInterval(() => {
      const a = anchor.current;
      if (a.paused) return;
      setPos(Math.min(state.duration, a.pos + (Date.now() - a.at)));
    }, 500);
    return () => clearInterval(id);
  }, [state.duration]);
  return pos;
}

// Consistent SVG transport icons (emoji glyphs render with colored boxes and
// don't align). All inherit the button color via currentColor.
function CtlIcon({ name, size = 15 }) {
  const shapes = {
    shuffle: (
      <g fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="16 3 21 3 21 8" /><line x1="4" y1="20" x2="21" y2="3" />
        <polyline points="21 16 21 21 16 21" /><line x1="15" y1="15" x2="21" y2="21" />
        <line x1="4" y1="4" x2="9" y2="9" />
      </g>
    ),
    prev: <g fill="currentColor"><polygon points="19 5 9 12 19 19" /><rect x="6" y="5" width="2.2" height="14" rx="1" /></g>,
    next: <g fill="currentColor"><polygon points="5 5 15 12 5 19" /><rect x="15.8" y="5" width="2.2" height="14" rx="1" /></g>,
    // centroid ~x=10.7 so the right-pointing triangle reads optically centered.
    play: <polygon fill="currentColor" points="7 4.5 19 12 7 19.5" />,
    pause: <g fill="currentColor"><rect x="6.5" y="5" width="3.5" height="14" rx="1" /><rect x="14" y="5" width="3.5" height="14" rx="1" /></g>,
  };
  return <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden="true">{shapes[name]}</svg>;
}

// Animated equalizer that sits next to the track name; bars move only while playing.
function Wave({ active }) {
  return (
    <span className={`sp-wave ${active ? "on" : ""}`} aria-hidden="true">
      <i /><i /><i /><i /><i />
    </span>
  );
}

function SpVolIcon({ muted }) {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polygon points="11,5 6,9 2,9 2,15 6,15 11,19" fill="currentColor" stroke="none" />
      {muted
        ? (<><line x1="17" y1="9" x2="23" y2="15" /><line x1="23" y1="9" x2="17" y2="15" /></>)
        : (<><path d="M15.5 8.5a5 5 0 0 1 0 7" fill="none" /><path d="M18.5 5.5a9 9 0 0 1 0 13" fill="none" /></>)}
    </svg>
  );
}

// Spotify-only volume: a mute toggle + a horizontal slider. Independent of the
// RAMBO voice volume in the Settings gear.
function SpVolume() {
  const [vol, setVol] = useState(spotify.getMusicVolume());
  const onChange = (e) => {
    const v = parseInt(e.target.value, 10);
    spotify.setMusicVolume(v);
    setVol(v);
  };
  const onMute = async () => { setVol(await spotify.toggleMusicMute()); };
  const muted = vol <= 0;
  return (
    <div className="sp-vol-row">
      <button className="sp-btn sp-mini" onClick={onMute}
        title={muted ? "Unmute music" : "Mute music"} aria-label="Mute Spotify">
        <SpVolIcon muted={muted} />
      </button>
      <input className="sp-vol-slider" type="range" min="0" max="100" step="5"
        value={vol} onChange={onChange} aria-label="Spotify volume" />
      <span className="sp-vol-val">{vol}%</span>
    </div>
  );
}

export default function SpotifyWidget({ compact = false }) {
  const state = useSpotifyState();
  const pos = useProgress(state);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [playlists, setPlaylists] = useState([]);
  const [expanded, setExpanded] = useState(null);
  const [tracks, setTracks] = useState({});   // id -> [tracks] | "error" | "empty"
  const [likedOpen, setLikedOpen] = useState(false);
  const [likedTracks, setLikedTracks] = useState(null);  // null | [tracks] | "error" | "empty"

  const loadPlaylists = useCallback(async () => {
    const data = await spotify.getPlaylists();
    setPlaylists((data.items || []).slice(0, 40));
  }, []);

  useEffect(() => {
    if (open && state.ready && playlists.length === 0) loadPlaylists();
  }, [open, state.ready, playlists.length, loadPlaylists]);

  const runSearch = async (e) => {
    e && e.preventDefault();
    const q = query.trim();
    if (!q) return;
    const data = await spotify.search(q);
    setResults(((data.tracks && data.tracks.items) || []).slice(0, 12));
  };

  const togglePlaylist = async (p) => {
    if (expanded === p.id) { setExpanded(null); return; }
    setExpanded(p.id);
    if (!tracks[p.id]) {
      const data = await spotify.getPlaylistTracks(p.id);
      let val;
      if (data && data.error) val = "error";
      else {
        const list = (data.items || []).map((it) => it.track).filter(Boolean);
        val = list.length ? list : "empty";
      }
      setTracks((prev) => ({ ...prev, [p.id]: val }));
    }
  };

  const toggleLiked = async () => {
    if (likedOpen) { setLikedOpen(false); return; }
    setLikedOpen(true);
    if (!likedTracks) {
      const data = await spotify.getLiked();
      let val;
      if (data && data.error) val = "error";
      else {
        const list = (data.items || []).map((it) => it.track).filter(Boolean);
        val = list.length ? list : "empty";
      }
      setLikedTracks(val);
    }
  };

  const onPlayPause = () => { if (state.track) spotify.togglePlay(); else spotify.playLiked(); };

  if (!state.configured) return null;

  if (!state.connected) {
    return (
      <div className={`spdg ${compact ? "spdg-compact" : ""}`}>
        <button className="sp-connect" onClick={spotify.connectSpotify}>
          <span className="sp-logo">♫</span> Connect Spotify
        </button>
      </div>
    );
  }

  if (state.error === "premium_required") {
    return (
      <div className={`spdg ${compact ? "spdg-compact" : ""}`}>
        <span className="sp-note">Spotify Premium required for in-app playback</span>
      </div>
    );
  }

  const art = state.art;
  const title = state.track || "";   // empty until something is actually playing
  const sub = state.artist || "";
  const playing = !state.paused && !!state.track;

  // Auto-surfaced when the saved token is missing a now-required scope.
  const reconnectBanner = state.needsReconnect ? (
    <div className="sp-reconnect-banner" onClick={spotify.reconnect}
      title="Your Spotify connection needs new permissions — click to reconnect">
      ⟳ Reconnect Spotify to enable Liked Songs
    </div>
  ) : null;

  const Art = ({ small }) => (
    <div className={`sp-art ${small ? "sp-art-sm" : ""}`}>
      {art ? <img src={art} alt="" /> : <span>♫</span>}
    </div>
  );

  const Controls = (
    <div className="sp-controls">
      <button className={`sp-btn sp-mini ${state.shuffle ? "sp-on" : ""}`} onClick={spotify.toggleShuffle} title="Shuffle"><CtlIcon name="shuffle" size={14} /></button>
      <button className="sp-btn" onClick={spotify.prevTrack} title="Previous"><CtlIcon name="prev" /></button>
      <button className="sp-btn sp-play" onClick={onPlayPause} title="Play/Pause"><CtlIcon name={playing ? "pause" : "play"} size={14} /></button>
      <button className="sp-btn" onClick={spotify.nextTrack} title="Next"><CtlIcon name="next" /></button>
    </div>
  );

  if (compact) {
    return (
      <div className="spdg spdg-compact">
        <Art small />
        <div className="sp-meta">
          <div className="sp-titlerow">
            <div className="sp-title" title={title}>{title}</div>
            <Wave active={playing} />
          </div>
          <div className="sp-sub" title={sub}>{sub}</div>
        </div>
        {Controls}
      </div>
    );
  }

  const pct = state.duration ? Math.min(100, (pos / state.duration) * 100) : 0;

  return (
    <div className="spdg">
      {reconnectBanner}
      <div className="sp-main">
        <Art />
        <div className="sp-body">
          <div className="sp-meta">
            <div className="sp-titlerow">
              <div className="sp-title" title={title}>{title}</div>
              <Wave active={playing} />
            </div>
            <div className="sp-sub" title={sub}>{sub}</div>
          </div>
          <div className="sp-seek">
            <span className="sp-time">{fmt(pos)}</span>
            <div className="sp-bar" onClick={(e) => {
              const r = e.currentTarget.getBoundingClientRect();
              spotify.seek(Math.round(((e.clientX - r.left) / r.width) * state.duration));
            }}>
              <div className="sp-bar-fill" style={{ width: `${pct}%` }} />
            </div>
            <span className="sp-time">{fmt(state.duration)}</span>
          </div>
          <SpVolume />
          <div className="sp-row">
            {Controls}
            <button className={`sp-toggle ${open ? "on" : ""}`} onClick={() => setOpen((o) => !o)}>
              {open ? "▾ Library" : "▸ Library"}
            </button>
          </div>
        </div>
      </div>

      {open && (
        <div className="sp-panel">
          <form className="sp-search" onSubmit={runSearch}>
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search songs…" spellCheck={false} />
            <button type="submit">🔍</button>
          </form>

          {results.length > 0 && (
            <div className="sp-list">
              <div className="sp-list-label">RESULTS</div>
              {results.map((t) => (
                <div key={t.id} className="sp-item" onClick={() =>
                  spotify.playUri(t.album && t.album.uri
                    ? { context_uri: t.album.uri, offset: { uri: t.uri } }
                    : { uris: [t.uri] })}>
                  <span className="sp-item-name">{t.name}</span>
                  <span className="sp-item-sub">{(t.artists || []).map((a) => a.name).join(", ")}</span>
                </div>
              ))}
            </div>
          )}

          <div className="sp-list sp-lib">
            <div className="sp-list-head">
              <span className="sp-list-label">YOUR LIBRARY</span>
              <button className="sp-reconnect" onClick={spotify.reconnect} title="Reconnect Spotify (re-grant permissions)">⟳ reconnect</button>
            </div>
            <div>
              <div className="sp-item sp-pl sp-liked" onClick={toggleLiked}>
                <span className="sp-item-name">{likedOpen ? "▾ " : "▸ "}♥ Liked Songs</span>
                <span className="sp-pl-play" title="Play Liked Songs"
                  onClick={(e) => { e.stopPropagation(); spotify.playLiked(); }}>▶</span>
              </div>
              {likedOpen && (
                <div className="sp-tracks">
                  {!likedTracks
                    ? <div className="sp-empty">{"// loading…"}</div>
                    : likedTracks === "error"
                      ? <div className="sp-empty">{"// click ⟳ reconnect above to grant Liked Songs access"}</div>
                      : likedTracks === "empty"
                        ? <div className="sp-empty">{"// no liked songs yet"}</div>
                        : likedTracks.map((t, i) => (
                          <div key={t.uri + i} className="sp-item sp-track"
                            onClick={() => spotify.playUri({ uris: likedTracks.slice(i, i + 100).map((x) => x.uri) })}>
                            <span className="sp-item-name">{t.name}</span>
                            <span className="sp-item-sub">{(t.artists || []).map((a) => a.name).join(", ")}</span>
                          </div>
                        ))}
                </div>
              )}
            </div>
            {playlists.length === 0
              ? <div className="sp-empty">{"// loading playlists…"}</div>
              : playlists.map((p) => (
                <div key={p.id}>
                  <div className="sp-item sp-pl" onClick={() => togglePlaylist(p)}>
                    <span className="sp-item-name">{expanded === p.id ? "▾ " : "▸ "}{p.name}</span>
                    <span className="sp-pl-play" title="Play this playlist"
                      onClick={(e) => { e.stopPropagation(); spotify.playUri({ context_uri: p.uri }); }}>▶</span>
                  </div>
                  {expanded === p.id && (
                    <div className="sp-tracks">
                      {!tracks[p.id]
                        ? <div className="sp-empty">{"// loading…"}</div>
                        : tracks[p.id] === "error"
                          ? <div className="sp-empty">{"// Spotify won't list this one — use ▶ to play it"}</div>
                          : tracks[p.id] === "empty"
                            ? <div className="sp-empty">{"// empty playlist"}</div>
                            : tracks[p.id].map((t, i) => (
                              <div key={t.uri + i} className="sp-item sp-track"
                                onClick={() => spotify.playUri({ context_uri: p.uri, offset: { uri: t.uri } })}>
                                <span className="sp-item-name">{t.name}</span>
                                <span className="sp-item-sub">{(t.artists || []).map((a) => a.name).join(", ")}</span>
                              </div>
                            ))}
                    </div>
                  )}
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}

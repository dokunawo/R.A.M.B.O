"""Spotify Web API client — OAuth (Authorization Code flow) plus the playback,
search, and playlist calls the R.A.M.B.O widget needs.

The backend holds the refresh token (in spotify_repo) and mints short-lived
access tokens. The browser's Web Playback SDK fetches an access token from
/spotify/token; all control/search/playlist calls are proxied through here so
the secret never leaves the server.

Everything is best-effort and returns plain dicts; callers surface errors to the
HUD rather than crashing the request path.
"""

from __future__ import annotations

import base64
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

_AUTH_URL = "https://accounts.spotify.com/authorize"
_TOKEN_URL = "https://accounts.spotify.com/api/token"
_API = "https://api.spotify.com/v1"

# Web Playback SDK needs `streaming` (+ account scopes); the rest cover control,
# now-playing, and reading the user's playlists.
SCOPES = (
    "streaming user-read-email user-read-private "
    "user-read-playback-state user-modify-playback-state user-read-currently-playing "
    "user-library-read "  # Liked Songs (/me/tracks)
    "playlist-read-private playlist-read-collaborative"
)


def client_id() -> str:
    return os.environ.get("SPOTIFY_CLIENT_ID", "").strip()


def client_secret() -> str:
    return os.environ.get("SPOTIFY_CLIENT_SECRET", "").strip()


def redirect_uri() -> str:
    return os.environ.get(
        "SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8000/spotify/callback"
    ).strip()


def is_configured() -> bool:
    return bool(client_id() and client_secret())


def _basic_auth() -> str:
    raw = f"{client_id()}:{client_secret()}".encode()
    return base64.b64encode(raw).decode()


class SpotifyClient:
    def __init__(self, repo):
        self._repo = repo

    # ── OAuth ────────────────────────────────────────────────────────
    def authorize_url(self, state: str) -> str:
        params = {
            "response_type": "code",
            "client_id": client_id(),
            "scope": SCOPES,
            "redirect_uri": redirect_uri(),
            "state": state,
            # Force the consent screen so newly-added scopes are actually granted
            # when an already-connected user reconnects.
            "show_dialog": "true",
        }
        return f"{_AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> bool:
        """Trade an auth code for tokens and persist them. Returns success."""
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri(),
        }
        token = await self._token_request(data)
        if not token or "refresh_token" not in token:
            return False
        await self._store(token, refresh_fallback=token.get("refresh_token", ""))
        return True

    async def _token_request(self, data: dict) -> dict | None:
        try:
            async with httpx.AsyncClient(timeout=15.0) as c:
                r = await c.post(
                    _TOKEN_URL,
                    data=data,
                    headers={
                        "Authorization": f"Basic {_basic_auth()}",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                )
                r.raise_for_status()
                return r.json()
        except Exception:
            logger.exception("Spotify token request failed")
            return None

    async def _store(self, token: dict, refresh_fallback: str) -> None:
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=token.get("expires_in", 3600))
        ).isoformat()
        await self._repo.save_tokens(
            refresh_token=token.get("refresh_token") or refresh_fallback,
            access_token=token.get("access_token", ""),
            expires_at=expires_at,
            scope=token.get("scope", ""),
        )

    async def access_token(self) -> str | None:
        """Return a valid access token, refreshing if it's expired/near-expiry."""
        row = await self._repo.get()
        if not row:
            return None
        # Refresh when within 60s of expiry (or no expiry recorded).
        try:
            exp = datetime.fromisoformat(row["expires_at"])
            fresh = exp - datetime.now(timezone.utc) > timedelta(seconds=60)
        except Exception:
            fresh = False
        if fresh and row["access_token"]:
            return row["access_token"]

        token = await self._token_request({
            "grant_type": "refresh_token",
            "refresh_token": row["refresh_token"],
        })
        if not token:
            return None
        await self._store(token, refresh_fallback=row["refresh_token"])
        return token.get("access_token")

    async def is_connected(self) -> bool:
        return (await self._repo.get()) is not None

    async def needs_reconnect(self) -> bool:
        """True when connected but the stored token is missing one of the scopes
        we now require (e.g. a scope added after the user first authorized) — so
        the UI can auto-surface a reconnect instead of failing silently."""
        row = await self._repo.get()
        if not row:
            return False
        have = set((row.get("scope") or "").split())
        return not set(SCOPES.split()).issubset(have)

    # ── Web API helpers ──────────────────────────────────────────────
    async def _request(self, method: str, path: str, *, params=None, json=None) -> dict:
        tok = await self.access_token()
        if not tok:
            return {"error": "not_connected"}
        try:
            async with httpx.AsyncClient(timeout=15.0) as c:
                r = await c.request(
                    method, f"{_API}{path}",
                    params=params, json=json,
                    headers={"Authorization": f"Bearer {tok}"},
                )
        except Exception:
            logger.exception("Spotify request error: %s %s", method, path)
            return {"error": "request_failed"}

        if r.status_code >= 400:
            return {"error": f"http_{r.status_code}", "detail": r.text[:200]}
        # Any 2xx is success. Player-control endpoints (next/previous/pause/play/
        # shuffle) return 204 OR 200 with a non-JSON body — don't choke on it.
        if r.status_code == 204 or not r.content:
            return {"ok": True}
        try:
            return r.json()
        except Exception:
            return {"ok": True}

    # ── High-level calls ─────────────────────────────────────────────
    async def devices(self) -> dict:
        return await self._request("GET", "/me/player/devices")

    async def resolve_device(self, preferred: str | None = None) -> str | None:
        """Pick a live device to play on. Prefers the currently-active device,
        then the caller's registered one if still online, then any 'R.A.M.B.O'
        web player. Avoids targeting a stale device id (the cause of 'says it's
        playing but nothing happens' when several R.A.M.B.O tabs exist)."""
        data = await self.devices()
        devs = data.get("devices", []) if isinstance(data, dict) else []
        if not devs:
            return preferred
        # Prefer the R.A.M.B.O browser player so playback lands where the widget's
        # SDK controls (next/prev/pause) actually apply — NOT on the phone, even if
        # the phone is the "active" device.
        if preferred and any(d.get("id") == preferred for d in devs):
            return preferred
        for d in devs:
            if d.get("name") == "R.A.M.B.O":
                return d["id"]
        for d in devs:
            if d.get("is_active"):
                return d["id"]
        return devs[0].get("id")

    async def shuffle(self, state: bool, device_id: str | None = None) -> dict:
        dev = await self.resolve_device(device_id)
        params = {"state": "true" if state else "false"}
        if dev:
            params["device_id"] = dev
        return await self._request("PUT", "/me/player/shuffle", params=params)

    async def now_playing(self) -> dict:
        return await self._request("GET", "/me/player")

    async def playlists(self, limit: int = 50) -> dict:
        return await self._request("GET", "/me/playlists", params={"limit": limit})

    async def playlist_tracks(self, playlist_id: str, limit: int = 100) -> dict:
        return await self._request(
            "GET", f"/playlists/{playlist_id}/tracks",
            params={"limit": limit, "fields": "items(track(name,uri,artists(name)))"},
        )

    async def liked(self, max_total: int = 500) -> dict:
        """The user's 'Liked Songs' (saved tracks). /me/tracks returns max 50 per
        call, so page through up to max_total. No playlist URI exists for these,
        so playback uses the track URIs directly."""
        items: list = []
        offset = 0
        while len(items) < max_total:
            page = await self._request(
                "GET", "/me/tracks", params={"limit": 50, "offset": offset},
            )
            if not isinstance(page, dict) or page.get("error"):
                if not items:
                    return page  # surface the error if we got nothing
                break
            batch = page.get("items", [])
            items.extend(batch)
            if len(batch) < 50:
                break
            offset += 50
        return {"items": items[:max_total]}

    async def search(self, q: str, type_: str = "track", limit: int = 10) -> dict:
        # Spotify caps search limit at 10 for development-mode apps; >10 → 400.
        return await self._request("GET", "/search", params={"q": q, "type": type_, "limit": min(limit, 10)})

    async def play(self, device_id: str | None = None, context_uri: str | None = None,
                   uris: list[str] | None = None, offset: dict | None = None) -> dict:
        # Resolve to a LIVE device (the passed id may be stale from a page reload),
        # so playback actually lands on the R.A.M.B.O player.
        dev = await self.resolve_device(device_id)
        if not dev:
            return {"error": "no_device"}
        body: dict = {}
        if context_uri:
            body["context_uri"] = context_uri
        if uris:
            body["uris"] = uris
        if offset:  # start position within a context/uris ({"uri":..} or {"position":N})
            body["offset"] = offset
        res = await self._request("PUT", "/me/player/play", params={"device_id": dev}, json=body or None)
        # If the device isn't active yet, Spotify 404s ("Device not found") — wake
        # it with a transfer, then retry once.
        if isinstance(res, dict) and str(res.get("error", "")).startswith("http_404"):
            await self.transfer(dev, play=False)
            res = await self._request("PUT", "/me/player/play", params={"device_id": dev}, json=body or None)
        return res

    async def pause(self, device_id: str | None = None) -> dict:
        dev = await self.resolve_device(device_id)
        return await self._request("PUT", "/me/player/pause", params={"device_id": dev} if dev else None)

    async def next(self, device_id: str | None = None) -> dict:
        # Web API next respects the device's shuffle_state automatically.
        dev = await self.resolve_device(device_id)
        return await self._request("POST", "/me/player/next", params={"device_id": dev} if dev else None)

    async def previous(self, device_id: str | None = None) -> dict:
        dev = await self.resolve_device(device_id)
        return await self._request("POST", "/me/player/previous", params={"device_id": dev} if dev else None)

    async def transfer(self, device_id: str, play: bool = True) -> dict:
        """Move playback onto the R.A.M.B.O browser device."""
        return await self._request("PUT", "/me/player", json={"device_ids": [device_id], "play": play})

    async def play_liked(self, device_id: str | None = None) -> dict:
        """Play the user's Liked Songs. Spotify's play accepts up to 100 uris, so
        queue the 100 most-recent saved tracks (next/prev advance through them)."""
        data = await self.liked(max_total=100)
        items = data.get("items", []) if isinstance(data, dict) else []
        uris = [it["track"]["uri"] for it in items if it.get("track")]
        if not uris:
            return {"error": "no_liked_songs"}
        return await self.play(device_id=device_id, uris=uris)

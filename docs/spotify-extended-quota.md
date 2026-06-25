# Unlocking Spotify Playlist Listings (Extended Quota Mode)

## The problem

RAMBO can list your **Liked Songs** but not the tracks inside your **playlists**.
The widget shows `// Spotify won't list this one — use ▶ to play it`.

This is **not a RAMBO bug.** The Spotify Web API endpoint
`GET /playlists/{id}/tracks` returns **403 Forbidden for every playlist** —
including playlists you own — when an app is in **Development Mode**. Verified
directly against a raw access token, bypassing all RAMBO code.

`Liked Songs` works only because it uses a different endpoint (`/me/tracks`),
which Development Mode does not restrict. Playing a playlist via its ▶ button
also still works, because that uses the playlist URI (`context_uri`), not the
track list.

## The fix: request Extended Quota Mode

Development Mode is the default for new Spotify apps and caps you to a small
allowlist of users plus a restricted set of endpoints. **Extended Quota Mode**
lifts those restrictions.

### Steps

1. Go to the **Spotify Developer Dashboard**: https://developer.spotify.com/dashboard
2. Log in and open the RAMBO app (the one whose `SPOTIFY_CLIENT_ID` is in
   `rambo-backend/.env`).
3. Click **Settings** → scroll to the app status / quota section, or open the
   **"Extended Quota Mode"** request form (Spotify also surfaces it as
   *"Request extension"* near the app's user-quota indicator).
4. Fill out the request:
   - **What the app does:** personal AI assistant / in-app music player using the
     Web Playback SDK; reads the user's own playlists and liked songs for voice
     control and an in-app player.
   - **Commercial / personal:** personal use.
   - **Where it runs:** localhost (`http://localhost:8000`, `http://localhost:3001`).
   - Accept the Spotify Developer Terms.
5. Submit. Spotify reviews manually — turnaround is typically a few business days.

### After approval

No code changes are needed. Once the app is in Extended Quota Mode the same
`/playlists/{id}/tracks` calls start returning data, and the widget's playlist
rows will expand and list tracks automatically (the `403 → "won't list this one"`
fallback simply stops firing).

## If you don't want to wait

Development Mode is fine for everything except *listing* playlist tracks:

- Playing whole playlists works (▶ on the playlist row).
- Liked Songs listing + per-song play works.
- Search + play works.

So Extended Quota Mode is only required if you specifically want to **see and
click individual tracks inside playlists** from the RAMBO widget.

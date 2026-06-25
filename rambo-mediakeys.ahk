#Requires AutoHotkey v2.0
; rambo-mediakeys.ahk — route the hardware media keys to the R.A.M.B.O player.
;
; Why this exists: R.A.M.B.O plays Spotify through the Web Playback SDK, whose
; audio lives in a CROSS-ORIGIN iframe that owns the browser's media session.
; Chrome won't hand our page the hardware play/pause key, so in-browser handling
; is unreliable. This script intercepts the media keys at the OS level and calls
; the R.A.M.B.O backend directly, which controls the web player via the Spotify
; Web API. Reliable, and independent of which window has focus.
;
; Launch: started automatically by rambo-startup.ps1. To run by hand:
;   "C:\Program Files\AutoHotkey\v2\AutoHotkey.exe" rambo-mediakeys.ahk
; Requires AutoHotkey v2 (https://www.autohotkey.com/).

API := "http://localhost:8000"

; ── One-shot boot gesture ────────────────────────────────────────────────────
; Chrome forbids starting screen capture (getDisplayMedia) without a user gesture,
; so RAMBO can't auto-share at page load. This sends a single harmless {F15} keydown
; to the RAMBO window a few seconds after boot — F15 produces no character and is no
; app shortcut, but DOES count as a user activation, which trips the app's armed
; auto-start so screen share begins with zero clicks. Title set via public/index.html.
SetTimer(BootGesture, -5000)   ; negative = run once, 5s after the script starts
BootGesture() {
    if WinExist("R.A.M.B.O ahk_exe chrome.exe") {
        WinActivate
        Sleep 250
        Send "{F15}"
    }
}

post(path) {
    try {
        req := ComObject("WinHttp.WinHttpRequest.5.1")
        req.Open("POST", API . path, false)
        req.SetRequestHeader("Content-Type", "application/json")
        req.SetTimeouts(2000, 2000, 2000, 4000)
        req.Send("{}")
    } catch {
        ; Backend not up yet / offline — let the keypress do nothing rather than error.
    }
}

; The "::" remaps SUPPRESS the key's default action, so it no longer reaches the
; Spotify SDK iframe — every press now drives the R.A.M.B.O player only.
Media_Play_Pause:: post("/spotify/toggle")
Media_Next::       post("/spotify/next")
Media_Prev::       post("/spotify/previous")

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
; so RAMBO can't auto-share at page load. This waits for the R.A.M.B.O window, lets
; the React app load and arm its auto-start listener, then performs ONE real click
; at a neutral spot — a guaranteed user activation that trips the share with zero
; clicks from the operator. Title is set via rambo-frontend/public/index.html.
SetTitleMatchMode 2            ; match a window whose title CONTAINS "R.A.M.B.O"
SetTimer(BootGesture, -1000)   ; negative = run once, ~1s after the script starts
BootGesture() {
    win := "R.A.M.B.O ahk_exe chrome.exe"
    if !WinWait(win, , 40)     ; wait up to 40s for the kiosk window to appear
        return
    Sleep 4000                 ; give the app time to load + arm armAutoStart()
    if !WinExist(win)
        return
    WinActivate win
    Sleep 300
    WinGetPos &x, &y, &w, &h, win
    ; Neutral target: horizontal center, upper-third — clear of the orb's mic button
    ; (center-bottom), the agent roster (left edge), and system params (right edge).
    Click x + w // 2, y + (h * 38 // 100)
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

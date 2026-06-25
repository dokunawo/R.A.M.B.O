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
SetTimer(PollOpenQueue, 2000)  ; every 2s: open any folders RAMBO asked to open
BootGesture() {
    win := "R.A.M.B.O ahk_exe chrome.exe"
    ; Wait up to 5 min: the helper is now launched BEFORE the browser (front-loaded
    ; in rambo-startup.ps1), so on a cold boot the window may take a while to appear
    ; while Docker + the frontend come up. Hotkeys stay responsive during this wait.
    if !WinWait(win, , 300)
        return
    ; Wait for the React app to actually LOAD and arm its screen-share listener —
    ; it POSTs /ui/ready when ready. Polling this (not a fixed sleep) is what stops
    ; the click from landing on a blank, not-yet-loaded page. Poll up to ~120s.
    ready := false
    loop 240 {
        if uiReady() {
            ready := true
            break
        }
        Sleep 500
    }
    if !ready
        return
    Sleep 1200                 ; let Phase 1 paint settle before the click
    if !WinExist(win)
        return
    WinActivate win
    Sleep 300
    WinGetPos &x, &y, &w, &h, win
    ; Neutral target: horizontal center, upper-third — clear of the orb's mic button
    ; (center-bottom), the agent roster (left edge), and system params (right edge).
    Click x + w // 2, y + (h * 38 // 100)
}

; True once the frontend has reported it's loaded (POSTed /ui/ready recently).
uiReady() {
    try {
        req := ComObject("WinHttp.WinHttpRequest.5.1")
        req.Open("GET", API . "/ui/ready", false)
        req.SetTimeouts(1500, 1500, 1500, 2500)
        req.Send()
        return InStr(req.ResponseText, '"ready":true') > 0
    } catch {
        return false
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

; ── Desktop-open bridge ──────────────────────────────────────────────────────
; RAMBO runs in Docker and can't open a window on the desktop. When the operator
; clicks "Open" on a built project (or a self-change), the backend queues the
; folder's Windows path; this poller drains the queue and opens each in VS Code,
; falling back to File Explorer if `code` isn't on PATH. The backend only ever
; queues paths inside the RAMBO repo, so nothing else can be opened.
PollOpenQueue() {
    try {
        req := ComObject("WinHttp.WinHttpRequest.5.1")
        req.Open("GET", API . "/desktop/open-queue", false)
        req.SetTimeouts(1500, 1500, 1500, 2500)
        req.Send()
        body := req.ResponseText
    } catch {
        return                  ; backend down — try again next tick
    }
    if !RegExMatch(body, '"open"\s*:\s*\[(.*?)\]', &m)
        return
    arr := m[1]
    pos := 1
    while RegExMatch(arr, '"((?:[^"\\]|\\.)*)"', &s, pos) {
        pos := s.Pos + s.Len
        path := StrReplace(StrReplace(s[1], "\\", "\"), "\/", "/")
        OpenPath(path)
    }
}

OpenPath(p) {
    ; `code "p" || explorer "p"` — VS Code if available, else Explorer. Run via
    ; cmd so `code` (a .cmd shim) resolves through PATH and the `||` fallback works.
    try Run(A_ComSpec . ' /c code "' . p . '" || explorer "' . p . '"', , "Hide")
}

; The "::" remaps SUPPRESS the key's default action, so it no longer reaches the
; Spotify SDK iframe — every press now drives the R.A.M.B.O player only.
Media_Play_Pause:: post("/spotify/toggle")
Media_Next::       post("/spotify/next")
Media_Prev::       post("/spotify/previous")

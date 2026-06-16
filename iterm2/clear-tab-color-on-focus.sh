#!/bin/bash
# Polls iTerm2 for the focused session's TTY; writes the OSC 6 reset escape
# whenever focus moves to a different tab/session, clearing whatever color
# peon-ping last set. Peon re-colors on the next Claude event.

set -uo pipefail

INTERVAL="${PEON_FOCUS_POLL_INTERVAL:-0.3}"
LAST_TTY=""

get_focused_tty() {
    osascript <<'APPLESCRIPT' 2>/dev/null
tell application "System Events"
    try
        set frontProc to name of first process whose frontmost is true
    on error
        return ""
    end try
end tell
if frontProc is not "iTerm2" then return ""
tell application "iTerm"
    try
        return tty of current session of current tab of current window
    on error
        return ""
    end try
end tell
APPLESCRIPT
}

while true; do
    tty=$(get_focused_tty)
    if [ -n "$tty" ] && [ "$tty" != "$LAST_TTY" ]; then
        printf '\033]6;1;bg;*;default\007' > "$tty" 2>/dev/null || true
        LAST_TTY="$tty"
    elif [ -z "$tty" ]; then
        LAST_TTY=""
    fi
    sleep "$INTERVAL"
done

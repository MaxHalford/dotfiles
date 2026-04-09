#!/usr/bin/env bash
# Claude Code Statusline - Based on https://github.com/pottekkat/claude-code-statusline
# Subscription mode (no cost/extra segments)

set -euo pipefail
export LC_NUMERIC=C

# ── Configuration ──────────────────────────────────────────────────────────────
CONFIG_FILE="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/statusline-config.json"
SETTINGS_FILE="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json"
CACHE_DIR="/tmp/claude-statusline"
CACHE_TTL=300

# ── Default config (overridden by config file) ────────────────────────────────
USE_NERDFONTS=true
SEGMENTS="agent,worktree,model,context,git,directory,duration,lines,tokens,effort,style,rate_5h,rate_7d"
CONTEXT_STYLE="bar"    # "bar" | "percent" | "tokens"
RATE_STYLE="bar"       # "bar" | "percent"

# ── NerdFont Icons ────────────────────────────────────────────────────────────
NF_ICON_MODEL="󱚡"
NF_ICON_CONTEXT="󰍛"
NF_ICON_GIT=""
NF_ICON_FOLDER=""
NF_ICON_CLOCK="󰥔"
NF_ICON_EFFORT=""
NF_ICON_AGENT="󰛦"
NF_ICON_WORKTREE="󰘬"
NF_ICON_VERSION="󰅩"
NF_ICON_STYLE="󰏘"
NF_ICON_TOKENS="󰚞"
NF_ICON_RATE="󰔟"
NF_ICON_DIRTY="*"
NF_ICON_BAR_FULL="█"
NF_ICON_BAR_EMPTY="░"

# ── Text Fallbacks ────────────────────────────────────────────────────────────
TXT_ICON_MODEL=""
TXT_ICON_CONTEXT="Ctx"
TXT_ICON_GIT=""
TXT_ICON_FOLDER=""
TXT_ICON_CLOCK=""
TXT_ICON_EFFORT=""
TXT_ICON_AGENT="Agent:"
TXT_ICON_WORKTREE="Worktree:"
TXT_ICON_VERSION="v"
TXT_ICON_STYLE="Style:"
TXT_ICON_TOKENS="Tokens:"
TXT_ICON_RATE=""
TXT_ICON_DIRTY="*"
TXT_ICON_BAR_FULL="#"
TXT_ICON_BAR_EMPTY="."

# ── Load config ───────────────────────────────────────────────────────────────
load_config() {
    if [[ -f "$CONFIG_FILE" ]]; then
        USE_NERDFONTS=$(jq -r 'if has("nerdfonts") then .nerdfonts else true end' "$CONFIG_FILE" 2>/dev/null || echo "true")
        SEGMENTS=$(jq -r '.segments // "agent,worktree,model,context,git,directory,duration,lines,tokens,effort,style,rate_5h,rate_7d"' "$CONFIG_FILE" 2>/dev/null || echo "agent,worktree,model,context,git,directory,duration,lines,tokens,effort,style,rate_5h,rate_7d")
        CONTEXT_STYLE=$(jq -r '.context_style // "bar"' "$CONFIG_FILE" 2>/dev/null || echo "bar")
        RATE_STYLE=$(jq -r '.rate_style // "bar"' "$CONFIG_FILE" 2>/dev/null || echo "bar")
    fi
}

# ── Read input ────────────────────────────────────────────────────────────────
INPUT=$(cat)
if [[ -z "$INPUT" ]]; then
    echo "Claude Code"
    exit 0
fi

load_config

# ── ANSI helpers ──────────────────────────────────────────────────────────────
reset="\033[0m"
bold="\033[1m"

red="\033[31m"
green="\033[32m"
yellow="\033[33m"
magenta="\033[35m"
cyan="\033[36m"
white="\033[37m"

br_black="\033[90m"
br_red="\033[91m"
br_green="\033[92m"
br_yellow="\033[93m"
br_blue="\033[94m"
br_magenta="\033[95m"
br_cyan="\033[96m"

# ── Resolve active icons ─────────────────────────────────────────────────────
setup_icons() {
    if [[ "$USE_NERDFONTS" == "true" ]]; then
        ICON_MODEL="$NF_ICON_MODEL"
        ICON_CONTEXT="$NF_ICON_CONTEXT"
        ICON_GIT="$NF_ICON_GIT"
        ICON_FOLDER="$NF_ICON_FOLDER"
        ICON_CLOCK="$NF_ICON_CLOCK"
        ICON_EFFORT="$NF_ICON_EFFORT"
        ICON_AGENT="$NF_ICON_AGENT"
        ICON_WORKTREE="$NF_ICON_WORKTREE"
        ICON_VERSION="$NF_ICON_VERSION"
        ICON_STYLE="$NF_ICON_STYLE"
        ICON_TOKENS="$NF_ICON_TOKENS"
        ICON_RATE="$NF_ICON_RATE"
        ICON_DIRTY="$NF_ICON_DIRTY"
        ICON_BAR_FULL="$NF_ICON_BAR_FULL"
        ICON_BAR_EMPTY="$NF_ICON_BAR_EMPTY"
    else
        ICON_MODEL="$TXT_ICON_MODEL"
        ICON_CONTEXT="$TXT_ICON_CONTEXT"
        ICON_GIT="$TXT_ICON_GIT"
        ICON_FOLDER="$TXT_ICON_FOLDER"
        ICON_CLOCK="$TXT_ICON_CLOCK"
        ICON_EFFORT="$TXT_ICON_EFFORT"
        ICON_AGENT="$TXT_ICON_AGENT"
        ICON_WORKTREE="$TXT_ICON_WORKTREE"
        ICON_VERSION="$TXT_ICON_VERSION"
        ICON_STYLE="$TXT_ICON_STYLE"
        ICON_TOKENS="$TXT_ICON_TOKENS"
        ICON_RATE="$TXT_ICON_RATE"
        ICON_DIRTY="$TXT_ICON_DIRTY"
        ICON_BAR_FULL="$TXT_ICON_BAR_FULL"
        ICON_BAR_EMPTY="$TXT_ICON_BAR_EMPTY"
    fi
}

# ── JSON helpers ──────────────────────────────────────────────────────────────
jval() {
    echo "$INPUT" | jq -r "$1 // empty" 2>/dev/null || true
}

jval_num() {
    local v
    v=$(echo "$INPUT" | jq -r "$1 // 0" 2>/dev/null || true)
    echo "${v:-0}"
}

icon() {
    local i="$1"
    if [[ -n "$i" ]]; then
        printf "%s " "$i"
    fi
}

# ── Progress bar ──────────────────────────────────────────────────────────────
progress_bar() {
    local pct=$1 width=${2:-8} color=${3:-$green}
    local filled=$(( pct * width / 100 ))
    if (( pct > 0 && filled == 0 )); then filled=1; fi
    local empty=$(( width - filled ))
    printf "%b" "${color}"
    for ((i=0; i<filled; i++)); do printf "%s" "${ICON_BAR_FULL}"; done
    printf "%b" "${br_black}"
    for ((i=0; i<empty; i++)); do printf "%s" "${ICON_BAR_EMPTY}"; done
    printf "%b" "${reset}"
}

mini_bar() {
    local pct=$1 color=${2:-$green}
    local width=5
    local filled=$(( pct * width / 100 ))
    if (( pct > 0 && filled == 0 )); then filled=1; fi
    local empty=$(( width - filled ))
    printf "%b" "${color}"
    for ((i=0; i<filled; i++)); do printf "%s" "${ICON_BAR_FULL}"; done
    printf "%b" "${br_black}"
    for ((i=0; i<empty; i++)); do printf "%s" "${ICON_BAR_EMPTY}"; done
    printf "%b" "${reset}"
}

color_by_pct() {
    local pct=$1
    if (( pct < 50 )); then echo -n "$green"
    elif (( pct < 70 )); then echo -n "$yellow"
    elif (( pct < 90 )); then echo -n "$br_yellow"
    else echo -n "$red"
    fi
}

fmt_tokens() {
    local n=$1
    if (( n >= 1000000 )); then
        printf "%d.%dM" $(( n / 1000000 )) $(( (n % 1000000) / 100000 ))
    elif (( n >= 1000 )); then
        printf "%d.%dk" $(( n / 1000 )) $(( (n % 1000) / 100 ))
    else
        printf "%d" "$n"
    fi
}

fmt_duration() {
    local ms=$1
    local secs=$(( ms / 1000 ))
    if (( secs < 60 )); then
        printf "%ds" "$secs"
    elif (( secs < 3600 )); then
        printf "%dm%ds" $(( secs / 60 )) $(( secs % 60 ))
    else
        printf "%dh%dm" $(( secs / 3600 )) $(( (secs % 3600) / 60 ))
    fi
}

# Convert ISO or epoch to epoch seconds
to_epoch() {
    local val="$1"
    if [[ -z "$val" || "$val" == "null" || "$val" == "0" ]]; then return 1; fi
    # If it's already a number (epoch), use it directly
    if [[ "$val" =~ ^[0-9]+$ ]]; then echo "$val"; return 0; fi
    # ISO timestamp — strip fractional seconds and timezone suffix
    local clean="${val%%.*}"
    clean="${clean%%Z}"
    clean="${clean%%+*}"
    if date -j -f "%Y-%m-%dT%H:%M:%S" "$clean" "+%s" 2>/dev/null; then return 0; fi
    date -d "$val" "+%s" 2>/dev/null || return 1
}

# "Resets in 3 hr 9 min" style relative countdown
fmt_reset_relative() {
    local val="$1"
    local epoch
    epoch=$(to_epoch "$val") || return
    local now diff
    now=$(date +%s)
    diff=$(( epoch - now ))
    if (( diff <= 0 )); then printf "now"; return; fi
    local days=$(( diff / 86400 ))
    local hours=$(( (diff % 86400) / 3600 ))
    local minutes=$(( (diff % 3600) / 60 ))
    if (( days > 0 )); then
        printf "in %d day %d hr" "$days" "$hours"
    elif (( hours > 0 )); then
        printf "in %d hr %d min" "$hours" "$minutes"
    else
        printf "in %d min" "$minutes"
    fi
}

# "Resets Tue 2:59 PM" style absolute day+time
fmt_reset_day_time() {
    local val="$1"
    local epoch
    epoch=$(to_epoch "$val") || return
    if date -j -f "%s" "$epoch" "+%a %l:%M %p" 2>/dev/null | sed 's/  / /g'; then return; fi
    date -d "@$epoch" "+%a %l:%M %p" 2>/dev/null | sed 's/  / /g' || true
}

# ── OAuth token resolution ────────────────────────────────────────────────────
get_oauth_token() {
    if [[ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]]; then
        echo "$CLAUDE_CODE_OAUTH_TOKEN"; return
    fi

    local config_dir="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
    local service_suffix=""
    if [[ -n "${CLAUDE_CONFIG_DIR:-}" ]]; then
        service_suffix="-$(echo -n "$CLAUDE_CONFIG_DIR" | { shasum -a 256 2>/dev/null || sha256sum; } | cut -d' ' -f1)"
    fi

    if command -v security &>/dev/null; then
        local raw parsed
        raw=$(security find-generic-password -s "Claude Code-credentials${service_suffix}" -w 2>/dev/null) || true
        if [[ -n "$raw" ]]; then
            parsed=$(echo "$raw" | jq -r '.claudeAiOauth.accessToken // empty' 2>/dev/null || true)
            if [[ -n "$parsed" ]]; then echo "$parsed"; return 0; fi
        fi
    fi

    local cred_file="$config_dir/.credentials.json"
    if [[ -f "$cred_file" ]]; then
        local file_token
        file_token=$(jq -r '.claudeAiOauth.accessToken // empty' "$cred_file" 2>/dev/null || true)
        if [[ -n "$file_token" ]]; then echo "$file_token"; return 0; fi
    fi

    if command -v secret-tool &>/dev/null; then
        local raw parsed
        raw=$(secret-tool lookup service "Claude Code-credentials${service_suffix}" 2>/dev/null) || true
        if [[ -n "$raw" ]]; then
            parsed=$(echo "$raw" | jq -r '.claudeAiOauth.accessToken // empty' 2>/dev/null || true)
            if [[ -n "$parsed" ]]; then echo "$parsed"; return 0; fi
        fi
    fi
    return 0
}

# ── Fetch usage data (cached) ────────────────────────────────────────────────
fetch_usage() {
    mkdir -p "$CACHE_DIR"
    local config_dir="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
    local cache_hash
    cache_hash=$(echo -n "$config_dir" | { shasum -a 256 2>/dev/null || sha256sum; } | cut -d' ' -f1 | head -c 8)
    local cache_file="$CACHE_DIR/statusline-cache-${cache_hash}.json"

    if [[ -f "$cache_file" ]]; then
        local cache_age=999
        if stat -f "%m" "$cache_file" &>/dev/null; then
            cache_age=$(( $(date +%s) - $(stat -f "%m" "$cache_file") ))
        elif stat -c "%Y" "$cache_file" &>/dev/null; then
            cache_age=$(( $(date +%s) - $(stat -c "%Y" "$cache_file") ))
        fi
        if (( cache_age < CACHE_TTL )); then
            cat "$cache_file"; return
        fi
    fi

    if ! command -v curl &>/dev/null; then
        if [[ -f "$cache_file" ]]; then cat "$cache_file"; else echo "{}"; fi
        return
    fi

    local token
    token=$(get_oauth_token)
    if [[ -z "$token" ]]; then
        if [[ -f "$cache_file" ]]; then cat "$cache_file"; else echo "{}"; fi
        return
    fi

    local response
    response=$(curl -sf --max-time 3 \
        -H "Authorization: Bearer $token" \
        -H "anthropic-beta: oauth-2025-04-20" \
        "https://api.anthropic.com/api/oauth/usage" 2>/dev/null) || response=""

    if [[ -n "$response" && "$response" != "{}" ]]; then
        echo "$response" > "$cache_file"
        echo "$response"
    elif [[ -f "$cache_file" ]]; then
        cat "$cache_file"
    else
        echo "{}"
    fi
}

# ── has_segment ───────────────────────────────────────────────────────────────
has_segment() {
    [[ ",$SEGMENTS," == *",$1,"* ]]
}

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
main() {
    setup_icons

    local MODEL_NAME MODEL_ID CWD CTX_SIZE CTX_PCT
    local CTX_INPUT CTX_CACHE_CREATE CTX_CACHE_READ TOTAL_INPUT TOTAL_OUTPUT
    local DURATION_MS API_DURATION_MS LINES_ADD LINES_DEL
    local RATE_5H_PCT RATE_5H_RESET RATE_7D_PCT RATE_7D_RESET
    local VERSION OUTPUT_STYLE AGENT_NAME WORKTREE_NAME WORKTREE_BRANCH

    MODEL_NAME=$(jval '.model.display_name')
    MODEL_ID=$(jval '.model.id')
    CWD=$(jval '.workspace.current_dir // .cwd')
    CTX_SIZE=$(jval_num '.context_window.context_window_size')
    CTX_PCT=$(jval_num '.context_window.used_percentage')
    CTX_INPUT=$(jval_num '.context_window.current_usage.input_tokens')
    CTX_CACHE_CREATE=$(jval_num '.context_window.current_usage.cache_creation_input_tokens')
    CTX_CACHE_READ=$(jval_num '.context_window.current_usage.cache_read_input_tokens')
    TOTAL_INPUT=$(jval_num '.context_window.total_input_tokens')
    TOTAL_OUTPUT=$(jval_num '.context_window.total_output_tokens')
    DURATION_MS=$(jval_num '.cost.total_duration_ms')
    API_DURATION_MS=$(jval_num '.cost.total_api_duration_ms')
    LINES_ADD=$(jval_num '.cost.total_lines_added')
    LINES_DEL=$(jval_num '.cost.total_lines_removed')
    RATE_5H_PCT=$(jval '.rate_limits.five_hour.used_percentage')
    RATE_5H_RESET=$(jval '.rate_limits.five_hour.resets_at')
    RATE_7D_PCT=$(jval '.rate_limits.seven_day.used_percentage')
    RATE_7D_RESET=$(jval '.rate_limits.seven_day.resets_at')
    VERSION=$(jval '.version')
    OUTPUT_STYLE=$(echo "$INPUT" | jq -r 'if .output_style | type == "object" then .output_style.name // empty elif .output_style | type == "string" then .output_style else empty end' 2>/dev/null || true)
    AGENT_NAME=$(jval '.agent.name')
    WORKTREE_NAME=$(jval '.worktree.name')
    WORKTREE_BRANCH=$(jval '.worktree.branch')

    local EFFORT=""
    if [[ -n "${CLAUDE_CODE_EFFORT_LEVEL:-}" ]]; then
        EFFORT="$CLAUDE_CODE_EFFORT_LEVEL"
    elif [[ -f "$SETTINGS_FILE" ]]; then
        EFFORT=$(jq -r '.effortLevel // empty' "$SETTINGS_FILE" 2>/dev/null) || true
    fi

    local AUTO_COMPACT_WINDOW=""
    local AUTO_COMPACT_PCT=""
    if [[ -f "$SETTINGS_FILE" ]]; then
        AUTO_COMPACT_WINDOW=$(jq -r '.env.CLAUDE_CODE_AUTO_COMPACT_WINDOW // empty' "$SETTINGS_FILE" 2>/dev/null) || true
        AUTO_COMPACT_PCT=$(jq -r '.env.CLAUDE_AUTOCOMPACT_PCT_OVERRIDE // empty' "$SETTINGS_FILE" 2>/dev/null) || true
    fi
    if [[ -n "$CWD" && -f "$CWD/.claude/settings.json" ]]; then
        local proj_acw proj_acp
        proj_acw=$(jq -r '.env.CLAUDE_CODE_AUTO_COMPACT_WINDOW // empty' "$CWD/.claude/settings.json" 2>/dev/null) || true
        proj_acp=$(jq -r '.env.CLAUDE_AUTOCOMPACT_PCT_OVERRIDE // empty' "$CWD/.claude/settings.json" 2>/dev/null) || true
        if [[ -n "$proj_acw" ]]; then AUTO_COMPACT_WINDOW="$proj_acw"; fi
        if [[ -n "$proj_acp" ]]; then AUTO_COMPACT_PCT="$proj_acp"; fi
    fi

    local EFFECTIVE_COMPACT_LIMIT=""
    if [[ -n "$AUTO_COMPACT_WINDOW" && "$AUTO_COMPACT_WINDOW" != "0" ]]; then
        local compact_pct="${AUTO_COMPACT_PCT:-83}"
        EFFECTIVE_COMPACT_LIMIT=$(( AUTO_COMPACT_WINDOW * compact_pct / 100 ))
    fi

    # ── Git info ──────────────────────────────────────────────────────────────
    local GIT_BRANCH="" GIT_DIRTY="" GIT_AHEAD=0 GIT_BEHIND=0
    if [[ -n "$CWD" ]] && command -v git &>/dev/null; then
        GIT_BRANCH=$(git -C "$CWD" --no-optional-locks symbolic-ref --short HEAD 2>/dev/null) || true
        if [[ -n "$GIT_BRANCH" ]]; then
            if [[ -n $(git -C "$CWD" --no-optional-locks status --porcelain 2>/dev/null) ]]; then
                GIT_DIRTY="true"
            fi
            local counts
            counts=$(git -C "$CWD" --no-optional-locks rev-list --left-right --count HEAD...@{upstream} 2>/dev/null) || true
            if [[ -n "$counts" ]]; then
                GIT_AHEAD=$(echo "$counts" | cut -f1)
                GIT_BEHIND=$(echo "$counts" | cut -f2)
            fi
        fi
    fi

    local DIR_NAME=""
    if [[ -n "$CWD" ]]; then DIR_NAME=$(basename "$CWD"); fi

    # ── Helpers ────────────────────────────────────────────────────────────────
    local LINE=""
    _append() {
        if [[ -n "$LINE" ]]; then LINE+="  "; fi
        LINE+="$1"
    }
    _flush() {
        if [[ -n "$LINE" ]]; then printf "%b\n" "$LINE"; fi
        LINE=""
    }

    # ══ LINE 1: Model, context, git, directory ════════════════════════════════

    if has_segment "agent" && [[ -n "$AGENT_NAME" ]]; then
        _append "${white}$(icon "$ICON_AGENT")${br_magenta}${AGENT_NAME}${reset}"
    fi

    if has_segment "worktree" && [[ -n "$WORKTREE_NAME" ]]; then
        local wt="${WORKTREE_NAME}"
        if [[ -n "$WORKTREE_BRANCH" ]]; then wt+=" (${WORKTREE_BRANCH})"; fi
        _append "${white}$(icon "$ICON_WORKTREE")${br_cyan}${wt}${reset}"
    fi

    if has_segment "model" && [[ -n "$MODEL_NAME" ]]; then
        local model_color="$br_blue"
        case "$MODEL_ID" in
            *opus*)   model_color="$br_magenta";;
            *sonnet*) model_color="$br_blue";;
            *haiku*)  model_color="$br_green";;
        esac

        local clean_name="${MODEL_NAME/ (1M context)/}"
        local model_text="$(icon "$ICON_MODEL")${clean_name}"

        local ctx_label=""
        if [[ -n "$EFFECTIVE_COMPACT_LIMIT" && "$EFFECTIVE_COMPACT_LIMIT" != "0" ]]; then
            local eff_k=$(( EFFECTIVE_COMPACT_LIMIT / 1000 ))
            if (( CTX_SIZE >= 1000000 )); then
                ctx_label="${eff_k}K/1M"
            elif (( CTX_SIZE > 0 )); then
                ctx_label="${eff_k}K/$(( CTX_SIZE / 1000 ))K"
            else
                ctx_label="${eff_k}K"
            fi
        elif (( CTX_SIZE >= 1000000 )); then
            ctx_label="1M"
        elif (( CTX_SIZE > 0 )); then
            ctx_label="$(( CTX_SIZE / 1000 ))K"
        fi

        if [[ -n "$ctx_label" ]]; then
            model_text+=" ${white}(${ctx_label})${reset}${model_color}"
        fi

        _append "${bold}${model_color}${model_text}${reset}"
    fi

    if has_segment "context"; then
        local pct=${CTX_PCT:-0}
        pct=${pct%.*}

        if [[ -n "$EFFECTIVE_COMPACT_LIMIT" && "$EFFECTIVE_COMPACT_LIMIT" != "0" ]]; then
            local used_tokens=$(( CTX_INPUT + CTX_CACHE_CREATE + CTX_CACHE_READ ))
            if (( used_tokens > 0 )); then
                pct=$(( used_tokens * 100 / EFFECTIVE_COMPACT_LIMIT ))
            elif (( CTX_SIZE > 0 )); then
                local used_approx=$(( pct * CTX_SIZE / 100 ))
                pct=$(( used_approx * 100 / EFFECTIVE_COMPACT_LIMIT ))
            fi
            if (( pct > 100 )); then pct=100; fi
        fi

        local ctx_color
        ctx_color=$(color_by_pct "$pct")

        local session_total=$(( TOTAL_INPUT + TOTAL_OUTPUT ))
        local session_str=""
        if (( session_total > 0 )); then
            session_str=" ${br_black}($(fmt_tokens $session_total) total)${reset}"
        fi

        case "$CONTEXT_STYLE" in
            bar)
                _append "${white}$(icon "$ICON_CONTEXT")${ctx_color}${pct}%${reset} $(progress_bar "$pct" 8 "$ctx_color")${session_str}"
                ;;
            percent)
                _append "${white}$(icon "$ICON_CONTEXT")${ctx_color}${pct}%${reset}${session_str}"
                ;;
            tokens)
                local used_tokens=$(( CTX_INPUT + CTX_CACHE_CREATE + CTX_CACHE_READ ))
                _append "${white}$(icon "$ICON_CONTEXT")${ctx_color}$(fmt_tokens $used_tokens)/$(fmt_tokens $CTX_SIZE)${reset}${session_str}"
                ;;
        esac
    fi

    if has_segment "git" && [[ -n "$GIT_BRANCH" ]]; then
        local git_text="${white}$(icon "$ICON_GIT")${green}${GIT_BRANCH}${reset}"
        if [[ "$GIT_DIRTY" == "true" ]]; then
            git_text+="${yellow}${ICON_DIRTY}${reset}"
        fi
        if (( GIT_AHEAD > 0 )); then
            git_text+=" ${br_green}↑${GIT_AHEAD}${reset}"
        fi
        if (( GIT_BEHIND > 0 )); then
            git_text+=" ${br_red}↓${GIT_BEHIND}${reset}"
        fi
        _append "$git_text"
    fi

    if has_segment "directory" && [[ -n "$DIR_NAME" ]]; then
        _append "${white}$(icon "$ICON_FOLDER")${cyan}${DIR_NAME}${reset}"
    fi

    _flush

    # ══ LINE 2: Session stats ═════════════════════════════════════════════════

    if has_segment "duration" && (( DURATION_MS > 1000 )); then
        local dur_text="${white}$(icon "$ICON_CLOCK")$(fmt_duration $DURATION_MS)${reset}"
        if has_segment "api_time" && (( API_DURATION_MS > 0 )); then
            local api_pct=$(( API_DURATION_MS * 100 / DURATION_MS ))
            dur_text+=" ${white}(API ${api_pct}%)${reset}"
        fi
        _append "$dur_text"
    fi

    if has_segment "lines" && (( LINES_ADD > 0 || LINES_DEL > 0 )); then
        local lines_text=""
        if (( LINES_ADD > 0 )); then
            lines_text+="${green}+${LINES_ADD}${reset}"
        fi
        if (( LINES_DEL > 0 )); then
            if (( LINES_ADD > 0 )); then lines_text+=" "; fi
            lines_text+="${red}-${LINES_DEL}${reset}"
        fi
        _append "$lines_text"
    fi

    if has_segment "tokens" && (( TOTAL_INPUT > 0 )); then
        _append "${white}$(icon "$ICON_TOKENS")${green}$(fmt_tokens $TOTAL_INPUT) ↑${reset}  ${br_yellow}$(fmt_tokens $TOTAL_OUTPUT) ↓${reset}"
    fi

    if has_segment "effort" && [[ -n "$EFFORT" && "$EFFORT" != "default" ]]; then
        case "$EFFORT" in
            high)   _append "${white}$(icon "$ICON_EFFORT")${magenta}High effort${reset}";;
            low)    _append "${white}$(icon "$ICON_EFFORT")Low effort${reset}";;
            medium) _append "${white}$(icon "$ICON_EFFORT")Medium effort${reset}";;
        esac
    fi

    if has_segment "version" && [[ -n "$VERSION" ]]; then
        _append "${white}$(icon "$ICON_VERSION")${VERSION}${reset}"
    fi

    if has_segment "style" && [[ -n "$OUTPUT_STYLE" && "$OUTPUT_STYLE" != "default" ]]; then
        _append "${white}$(icon "$ICON_STYLE")${OUTPUT_STYLE}${reset}"
    fi

    _flush

    # ══ LINE 3: Rate limits ═══════════════════════════════════════════════════

    if has_segment "rate_5h" || has_segment "rate_7d"; then
        local USAGE_DATA=""
        if [[ -z "$RATE_5H_PCT" && -z "$RATE_7D_PCT" ]]; then
            USAGE_DATA=$(fetch_usage)
        fi

        if has_segment "rate_5h"; then
            local pct_5h="" raw_5h_reset=""

            if [[ -n "$RATE_5H_PCT" ]]; then
                pct_5h="${RATE_5H_PCT%.*}"
                raw_5h_reset="$RATE_5H_RESET"
            elif [[ -n "$USAGE_DATA" ]]; then
                pct_5h=$(echo "$USAGE_DATA" | jq -r '.five_hour.utilization // empty' 2>/dev/null)
                pct_5h="${pct_5h%.*}"
                raw_5h_reset=$(echo "$USAGE_DATA" | jq -r '.five_hour.resets_at // empty' 2>/dev/null)
            fi

            if [[ -n "$pct_5h" ]]; then
                local rate_color
                rate_color=$(color_by_pct "$pct_5h")
                local rt="${white}$(icon "$ICON_RATE")5 Hour:${reset} ${rate_color}${pct_5h}%${reset}"
                if [[ "$RATE_STYLE" == "bar" ]]; then
                    rt+=" $(mini_bar "$pct_5h" "$rate_color")"
                fi
                if [[ -n "$raw_5h_reset" ]]; then
                    local rel
                    rel=$(fmt_reset_relative "$raw_5h_reset")
                    if [[ -n "$rel" ]]; then
                        rt+=" ${br_black}Resets ${rel}${reset}"
                    fi
                fi
                _append "$rt"
            fi
        fi

        if has_segment "rate_7d"; then
            local pct_7d="" raw_7d_reset=""

            if [[ -n "$RATE_7D_PCT" ]]; then
                pct_7d="${RATE_7D_PCT%.*}"
                raw_7d_reset="$RATE_7D_RESET"
            elif [[ -n "$USAGE_DATA" ]]; then
                pct_7d=$(echo "$USAGE_DATA" | jq -r '.seven_day.utilization // empty' 2>/dev/null)
                pct_7d="${pct_7d%.*}"
                raw_7d_reset=$(echo "$USAGE_DATA" | jq -r '.seven_day.resets_at // empty' 2>/dev/null)
            fi

            if [[ -n "$pct_7d" ]]; then
                local rate_color
                rate_color=$(color_by_pct "$pct_7d")
                local rt="${white}7 Day:${reset} ${rate_color}${pct_7d}%${reset}"
                if [[ "$RATE_STYLE" == "bar" ]]; then
                    rt+=" $(mini_bar "$pct_7d" "$rate_color")"
                fi
                if [[ -n "$raw_7d_reset" ]]; then
                    local day_time
                    day_time=$(fmt_reset_day_time "$raw_7d_reset")
                    if [[ -n "$day_time" ]]; then
                        rt+=" ${br_black}Resets ${day_time}${reset}"
                    fi
                fi
                _append "$rt"
            fi
        fi

        _flush
    fi
}

main

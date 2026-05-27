#!/usr/bin/env bash
# Nova CLI — shell hooks for command/output capture.
# Installed to ~/.nova/nova_hooks.sh and sourced from ~/.bashrc.

if [[ -n "${NOVA_HOOKS_ACTIVE:-}" ]]; then
    return 0 2>/dev/null || exit 0
fi
export NOVA_HOOKS_ACTIVE=1

if [[ -d /dev/shm ]] && [[ -w /dev/shm ]]; then
    NOVA_SESSION_DIR="/dev/shm/nova_$$"
else
    NOVA_SESSION_DIR="${HOME}/.nova/session/nova_$$"
fi
mkdir -p "$NOVA_SESSION_DIR"
export NOVA_SESSION_DIR

NOVA_CAPTURE_LOG="$NOVA_SESSION_DIR/capture.log"
: > "$NOVA_CAPTURE_LOG"
exec > >(stdbuf -oL -eL tee -a "$NOVA_CAPTURE_LOG" 2>/dev/null || tee -a "$NOVA_CAPTURE_LOG") 2>&1

_nova_cleanup() {
    rm -rf "$NOVA_SESSION_DIR"
}
trap _nova_cleanup EXIT

_nova_debug_trap() {
    local cmd="${BASH_COMMAND:-}"

    [[ "$cmd" == _nova_* ]] && return 0
    [[ "$cmd" == trap* ]] && return 0

    if [[ "$cmd" == nova\ * ]] || [[ "$cmd" == nova ]]; then
        _nova_skip_prompt_capture=1
        return 0
    fi

    _nova_skip_prompt_capture=
    printf '%s' "$cmd" > "$NOVA_SESSION_DIR/last_cmd"
    NOVA_CAPTURE_START=$(wc -c < "$NOVA_CAPTURE_LOG" 2>/dev/null | tr -d ' ')
    NOVA_CAPTURE_START=${NOVA_CAPTURE_START:-0}
}

_nova_prompt_command() {
    if [[ -n "${_nova_skip_prompt_capture:-}" ]]; then
        _nova_skip_prompt_capture=
        return 0
    fi

    if [[ -f "$NOVA_CAPTURE_LOG" ]]; then
        local start=${NOVA_CAPTURE_START:-0}
        tail -c +$((start + 1)) "$NOVA_CAPTURE_LOG" > "$NOVA_SESSION_DIR/last_output" 2>/dev/null || true
        sync "$NOVA_SESSION_DIR/last_output" 2>/dev/null || true
    fi
}

trap '_nova_debug_trap' DEBUG
PROMPT_COMMAND='_nova_last_exit=$?; _nova_prompt_command'

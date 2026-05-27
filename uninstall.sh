#!/bin/bash
# Nova CLI — full uninstall (run from anywhere)

set -euo pipefail

# Self-fix CRLF when executed as a file
if [[ -n "${BASH_SOURCE[0]:-}" && "${BASH_SOURCE[0]}" != "bash" && -f "${BASH_SOURCE[0]}" ]]; then
    sed -i 's/\r//' "${BASH_SOURCE[0]}" 2>/dev/null \
        || sed -i '' 's/\r//' "${BASH_SOURCE[0]}" 2>/dev/null \
        || true
fi

BASHRC="$HOME/.bashrc"
CONFIG_DIR="$HOME/.nova"
LOCAL_BIN="$HOME/.local/bin/nova"

echo "╔══════════════════════════════════════════╗"
echo "║         🗑️  Nova CLI Uninstaller         ║"
echo "╚══════════════════════════════════════════╝"
echo ""

echo "▶ Removing Nova CLI package..."
python3 -m pip uninstall -y nova-cli --break-system-packages 2>/dev/null \
    || echo "  (package not installed via pip)"

if [[ -f "$LOCAL_BIN" ]]; then
    rm -f "$LOCAL_BIN"
fi

echo "▶ Removing ~/.nova..."
if [[ -d "$CONFIG_DIR" ]]; then
    rm -rf "$CONFIG_DIR"
fi

echo "▶ Cleaning ~/.bashrc..."
if [[ -f "$BASHRC" ]]; then
    sed -i '/# Nova CLI Path/,+2d' "$BASHRC" 2>/dev/null \
        || sed -i '' '/# Nova CLI Path/,+2d' "$BASHRC" 2>/dev/null \
        || true
    sed -i '/# Nova CLI shell hooks/,+1d' "$BASHRC" 2>/dev/null \
        || sed -i '' '/# Nova CLI shell hooks/,+1d' "$BASHRC" 2>/dev/null \
        || true
    # Remove any stray hook source lines
    sed -i '\|source ~/.nova/nova_hooks.sh|d' "$BASHRC" 2>/dev/null \
        || sed -i '' '\|source ~/.nova/nova_hooks.sh|d' "$BASHRC" 2>/dev/null \
        || true
fi

echo ""
echo " ✓ Nova uninstalled cleanly"
echo ""

#!/bin/bash
# Nova CLI — full uninstall (no chmod needed; run from anywhere)
#
#   curl -fsSL https://raw.githubusercontent.com/vizakan10/Nova-support-tool/main/uninstall.sh | bash
#
#   cd Nova-support-tool && bash uninstall.sh

set -euo pipefail

# Self-fix CRLF when executed as a file
if [[ -n "${BASH_SOURCE[0]:-}" && "${BASH_SOURCE[0]}" != "bash" && -f "${BASH_SOURCE[0]}" ]]; then
    sed -i 's/\r//' "${BASH_SOURCE[0]}" 2>/dev/null \
        || sed -i '' 's/\r//' "${BASH_SOURCE[0]}" 2>/dev/null \
        || true
fi

BASHRC="$HOME/.bashrc"
CONFIG_DIR="$HOME/.nova"
SECRETS_FILE="$HOME/.nova/secrets.json"
LOCAL_BIN="$HOME/.local/bin/nova"

echo "╔══════════════════════════════════════════╗"
echo "║         🗑️  Nova CLI Uninstaller         ║"
echo "╚══════════════════════════════════════════╝"
echo ""

read -p "Type 'uninstall' to confirm: " confirm
if [[ "$confirm" != "uninstall" ]]; then
    echo "❌ Cancelled."
    exit 1
fi
echo ""

# ── 1. Pip uninstall ─────────────────────────────────────────────────────────
echo "▶ Removing Nova CLI package..."
python3 -m pip uninstall -y nova-cli --break-system-packages 2>/dev/null \
    || echo "  (package not installed via pip)"
if [[ -f "$LOCAL_BIN" ]]; then
    rm -f "$LOCAL_BIN"
fi

# ── 2. Secrets file ──────────────────────────────────────────────────────────
if [[ -f "$SECRETS_FILE" ]]; then
    read -p "❓ Delete secrets file (API keys)? ($SECRETS_FILE) [y/N]: " del_secrets
    if [[ "${del_secrets:-}" =~ ^[Yy]$ ]]; then
        rm -f "$SECRETS_FILE"
        echo "✅ Secrets file deleted."
    else
        echo "  Keeping secrets file."
    fi
fi

# ── 3. Cloned repo folder ────────────────────────────────────────────────────
CLONE_DIR=""
# Check common locations: curl install clone and home folder clone
for candidate in "$HOME/.nova/nova-src" "$HOME/Nova-support-tool"; do
    if [[ -d "$candidate" && -f "$candidate/setup.py" ]]; then
        CLONE_DIR="$candidate"
        break
    fi
done
# If running from inside a clone, offer that too
if [[ -z "$CLONE_DIR" && -f "$(pwd)/setup.py" && -f "$(pwd)/nova_cli.py" ]]; then
    CLONE_DIR="$(pwd)"
fi

if [[ -n "$CLONE_DIR" ]]; then
    read -p "❓ Delete cloned Nova folder? ($CLONE_DIR) [y/N]: " del_clone
    if [[ "${del_clone:-}" =~ ^[Yy]$ ]]; then
        cd "$HOME"
        rm -rf "$CLONE_DIR"
        echo "✅ Cloned folder deleted."
    else
        echo "  Keeping cloned folder."
    fi
fi

# ── 4. Remaining ~/.nova config ──────────────────────────────────────────────
if [[ -d "$CONFIG_DIR" ]]; then
    read -p "❓ Delete remaining config folder? ($CONFIG_DIR) [y/N]: " del_config
    if [[ "${del_config:-}" =~ ^[Yy]$ ]]; then
        rm -rf "$CONFIG_DIR"
        echo "✅ Config folder deleted."
    else
        echo "  Keeping config folder."
    fi
fi

# ── 5. Clean ~/.bashrc ────────────────────────────────────────────────────────
echo "▶ Cleaning ~/.bashrc..."
if [[ -f "$BASHRC" ]]; then
    sed -i '/# Nova CLI Path/,+2d' "$BASHRC" 2>/dev/null \
        || sed -i '' '/# Nova CLI Path/,+2d' "$BASHRC" 2>/dev/null \
        || true
    sed -i '/# Nova CLI shell hooks/,+1d' "$BASHRC" 2>/dev/null \
        || sed -i '' '/# Nova CLI shell hooks/,+1d' "$BASHRC" 2>/dev/null \
        || true
    sed -i '\|source ~/.nova/nova_hooks.sh|d' "$BASHRC" 2>/dev/null \
        || sed -i '' '\|source ~/.nova/nova_hooks.sh|d' "$BASHRC" 2>/dev/null \
        || true
fi

echo ""
echo " ✓ Nova uninstalled cleanly"
echo ""

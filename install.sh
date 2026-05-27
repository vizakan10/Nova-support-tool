#!/bin/bash
# Nova CLI — one-shot installer
# Usage: git clone ... && cd Nova-support-tool && chmod +x install.sh && ./install.sh

set -euo pipefail

HOOKS_FILE="$HOME/.nova/nova_hooks.sh"
HOOK_LINE="source ~/.nova/nova_hooks.sh"
LOCAL_BIN="$HOME/.local/bin"
BASHRC="$HOME/.bashrc"

die() {
    echo ""
    echo "❌ $1" >&2
    echo ""
    exit 1
}

step_ok() {
    echo "✅ $1"
}

echo "╔══════════════════════════════════════════╗"
echo "║          🚀  Nova CLI Installer          ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 1. Python 3 ─────────────────────────────────────────────────────────────
echo "▶ Checking Python 3..."
if ! command -v python3 &>/dev/null; then
    die "Python 3 is not installed. Install it first, e.g.:  sudo apt install python3 python3-pip"
fi
step_ok "Python 3 found: $(python3 --version 2>&1)"

# ── 2. PATH (~/.local/bin) ──────────────────────────────────────────────────
echo "▶ Configuring PATH..."
if [[ ":${PATH}:" != *":${LOCAL_BIN}:"* ]]; then
    if [[ -f "$BASHRC" ]] && grep -qF 'Nova CLI Path' "$BASHRC" 2>/dev/null; then
        step_ok "PATH entry already in ~/.bashrc"
    else
        {
            echo ""
            echo "# Nova CLI Path"
            echo 'export PATH="$HOME/.local/bin:$PATH"'
            echo "alias nova-r='source ~/.bashrc'"
        } >>"$BASHRC" || die "Could not write PATH to ~/.bashrc"
        step_ok "Added ~/.local/bin to ~/.bashrc"
    fi
fi
export PATH="${LOCAL_BIN}:${PATH}"

# ── 3. Pip install ──────────────────────────────────────────────────────────
echo "▶ Installing Nova CLI (pip)..."
if ! python3 -m pip install --user --break-system-packages -e .; then
    die "pip install failed. Check errors above and try again."
fi
if ! command -v nova &>/dev/null; then
    die "nova command not found after install. Ensure ~/.local/bin is on your PATH."
fi
step_ok "Nova CLI installed ($(nova version 2>/dev/null | tr -d '\n' || echo 'nova'))"

# ── 4. Shell hooks ────────────────────────────────────────────────────────────
echo "▶ Installing shell hooks..."
if ! nova install-hooks; then
    die "nova install-hooks failed."
fi
if [[ ! -f "$HOOKS_FILE" ]]; then
    die "Hooks file missing after install: $HOOKS_FILE"
fi
step_ok "Hooks installed to $HOOKS_FILE"

# ── 5. Strip CRLF (WSL / Windows checkout) ───────────────────────────────────
echo "▶ Normalizing hook line endings..."
if ! sed -i 's/\r$//' "$HOOKS_FILE" 2>/dev/null; then
    # macOS/BSD sed fallback (unlikely on WSL, but safe)
    if ! sed -i '' 's/\r$//' "$HOOKS_FILE" 2>/dev/null; then
        die "Could not strip \\r from $HOOKS_FILE"
    fi
fi
step_ok "Hook file uses Unix line endings"

# ── 6. Ensure ~/.bashrc sources hooks ───────────────────────────────────────
echo "▶ Configuring ~/.bashrc..."
if [[ ! -f "$BASHRC" ]]; then
    touch "$BASHRC" || die "Could not create ~/.bashrc"
fi
if grep -qF "$HOOK_LINE" "$BASHRC" 2>/dev/null; then
    step_ok "Hook source line already in ~/.bashrc"
else
    {
        echo ""
        echo "# Nova CLI shell hooks"
        echo "$HOOK_LINE"
    } >>"$BASHRC" || die "Could not append hook source line to ~/.bashrc"
    step_ok "Added hook source line to ~/.bashrc"
fi

# ── 7. Interactive setup (KB + AI) ──────────────────────────────────────────
echo ""
echo "▶ Running Nova setup (KB path + AI provider)..."
echo ""
if ! nova setup; then
    die "nova setup failed or was cancelled. Run 'nova setup' to try again."
fi
step_ok "Setup complete"

# ── 8. Done ─────────────────────────────────────────────────────────────────
echo ""
echo " ✓ Nova installed and ready"
echo ""
echo " Important: open a new terminal, or run:"
echo "   source ~/.bashrc"
echo ""
echo " Then try it:"
echo "   run any command that fails"
echo "   nova up"
echo ""

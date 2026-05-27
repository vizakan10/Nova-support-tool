#!/bin/bash
# Nova CLI — one-shot installer
#   curl -fsSL https://raw.githubusercontent.com/vizakan10/Nova-support-tool/main/install.sh | bash
#   git clone ... && cd Nova-support-tool && ./install.sh

set -euo pipefail

# Self-fix CRLF when executed as a file (skipped for curl | bash stdin)
if [[ -n "${BASH_SOURCE[0]:-}" && "${BASH_SOURCE[0]}" != "bash" && -f "${BASH_SOURCE[0]}" ]]; then
    sed -i 's/\r//' "${BASH_SOURCE[0]}" 2>/dev/null \
        || sed -i '' 's/\r//' "${BASH_SOURCE[0]}" 2>/dev/null \
        || true
fi

REPO_URL="https://github.com/vizakan10/Nova-support-tool.git"
REPO_DIR="${NOVA_SRC:-$HOME/.nova/nova-src}"
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

_strip_crlf() {
    local f="$1"
    [[ -f "$f" ]] || return 0
    if ! sed -i 's/\r//' "$f" 2>/dev/null; then
        if ! sed -i '' 's/\r//' "$f" 2>/dev/null; then
            die "Could not strip \\r from $f"
        fi
    fi
}

_in_repo() {
    [[ -f "${1}/setup.py" && -f "${1}/nova_cli.py" ]]
}

# curl | bash: clone source and re-exec the on-disk install.sh
if [[ "${BASH_SOURCE[0]:-}" == "bash" ]] || [[ ! -f "${BASH_SOURCE[0]:-}" ]]; then
    echo "▶ Fetching Nova source..."
    if ! command -v git &>/dev/null; then
        die "git is required for curl install. Install git first, e.g.:  sudo apt install git"
    fi
    mkdir -p "$(dirname "$REPO_DIR")"
    if [[ -d "$REPO_DIR/.git" ]]; then
        git -C "$REPO_DIR" pull --ff-only || die "git pull failed in $REPO_DIR"
        step_ok "Updated existing clone at $REPO_DIR"
    else
        git clone "$REPO_URL" "$REPO_DIR" || die "git clone failed"
        step_ok "Cloned to $REPO_DIR"
    fi
    exec bash "$REPO_DIR/install.sh"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! _in_repo "$SCRIPT_DIR"; then
    die "Not a Nova repo (missing setup.py). Run from a clone or use curl | bash."
fi

echo "╔══════════════════════════════════════════╗"
echo "║          🚀  Nova CLI Installer          ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 1. Strip CRLF from all repo shell scripts ───────────────────────────────
echo "▶ Normalizing shell script line endings..."
for sh in "$SCRIPT_DIR"/*.sh; do
    [[ -f "$sh" ]] && _strip_crlf "$sh"
done
step_ok "Shell scripts use Unix line endings"

# ── 2. Python 3 ─────────────────────────────────────────────────────────────
echo "▶ Checking Python 3..."
if ! command -v python3 &>/dev/null; then
    die "Python 3 is not installed. Install it first, e.g.:  sudo apt install python3 python3-pip"
fi
step_ok "Python 3 found: $(python3 --version 2>&1)"

# ── 3. PATH (~/.local/bin) ──────────────────────────────────────────────────
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

# ── 4. Pip install ──────────────────────────────────────────────────────────
echo "▶ Installing Nova CLI (pip)..."
if ! python3 -m pip install --user --break-system-packages -e .; then
    die "pip install failed. Check errors above and try again."
fi
if ! command -v nova &>/dev/null; then
    die "nova command not found after install. Ensure ~/.local/bin is on your PATH."
fi
step_ok "Nova CLI installed ($(nova version 2>/dev/null | tr -d '\n' || echo 'nova'))"

# ── 5. Shell hooks ────────────────────────────────────────────────────────────
echo "▶ Installing shell hooks..."
if ! nova install-hooks; then
    die "nova install-hooks failed."
fi
if [[ ! -f "$HOOKS_FILE" ]]; then
    die "Hooks file missing after install: $HOOKS_FILE"
fi
_strip_crlf "$HOOKS_FILE"
step_ok "Hooks installed to $HOOKS_FILE"

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
echo " ✓ Nova installed successfully"
echo ""
echo " One-time only: open a new terminal."
echo " (Hooks load automatically in every terminal after that — nothing to redo tomorrow.)"
echo ""
echo " Try it in that new terminal:"
echo "   python3 -c \"import nosuchmodule\""
echo "   nova up"
echo ""

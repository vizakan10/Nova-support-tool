#!/bin/bash
sed -i 's/\r//' "$0" 2>/dev/null || sed -i '' 's/\r//' "$0" 2>/dev/null || true
# Nova CLI — one-shot installer (no chmod needed)
#
# Option 1 — Binary install (recommended, no Python required):
#   mkdir -p ~/.local/bin
#   curl -L https://github.com/vizakan10/Nova-support-tool/releases/latest/download/nova -o ~/.local/bin/nova
#   chmod +x ~/.local/bin/nova
#   export PATH="$HOME/.local/bin:$PATH"
#   nova install-hooks
#   nova setup
#
# Option 2 — Source install (developers):
#   curl -fsSL https://raw.githubusercontent.com/vizakan10/Nova-support-tool/main/install.sh | bash
#   git clone https://github.com/vizakan10/Nova-support-tool.git
#   cd Nova-support-tool && bash install.sh
#
#   bash install.sh --binary   # download release binary instead of pip install

set -euo pipefail

NOVA_RELEASE_URL="https://github.com/vizakan10/Nova-support-tool/releases/latest/download/nova"

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

_nova_already_configured() {
    python3 - <<'PY' 2>/dev/null
import json
import os
import sys

path = os.path.expanduser("~/.nova/config.json")
if not os.path.isfile(path):
    sys.exit(1)
try:
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh)
except (json.JSONDecodeError, OSError):
    sys.exit(1)
sys.exit(0 if cfg.get("active_kb") else 1)
PY
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

_install_binary() {
    echo "╔══════════════════════════════════════════╗"
    echo "║     🚀  Nova CLI Installer (binary)      ║"
    echo "╚══════════════════════════════════════════╝"
    echo ""
    if [[ ":${PATH}:" != *":${LOCAL_BIN}:"* ]]; then
        if [[ -f "$BASHRC" ]] && ! grep -qF 'Nova CLI Path' "$BASHRC" 2>/dev/null; then
            {
                echo ""
                echo "# Nova CLI Path"
                echo 'export PATH="$HOME/.local/bin:$PATH"'
            } >>"$BASHRC" || true
        fi
    fi
    export PATH="${LOCAL_BIN}:${PATH}"
    echo "▶ Downloading nova binary..."
    mkdir -p "$LOCAL_BIN"
    if ! curl -fsSL "$NOVA_RELEASE_URL" -o "$LOCAL_BIN/nova"; then
        die "Download failed. Check network or build from source: bash install.sh"
    fi
    chmod +x "$LOCAL_BIN/nova"
    step_ok "Installed to $LOCAL_BIN/nova"
    export PATH="${LOCAL_BIN}:${PATH}"
    echo "▶ Installing shell hooks..."
    nova install-hooks || die "nova install-hooks failed"
    step_ok "Hooks installed"
    if ! _nova_already_configured; then
        echo ""
        echo "▶ Running Nova setup (KB path + AI provider)..."
        nova setup || die "nova setup failed"
        step_ok "Setup complete"
    fi
    echo ""
    echo " ✓ Nova binary installed successfully"
    echo "  Open a new terminal or: source ~/.bashrc"
    echo ""
}

if [[ "${1:-}" == "--binary" ]]; then
    _install_binary
    exit 0
fi

if ! _in_repo "$SCRIPT_DIR"; then
    die "Not a Nova repo (missing setup.py). Run from a clone, curl | bash, or: bash install.sh --binary"
fi

echo "╔══════════════════════════════════════════╗"
echo "║          🚀  Nova CLI Installer          ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "  Tip: release binary (no Python):  bash install.sh --binary"
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

# ── 4. Pip install (Nova + dependencies) ────────────────────────────────────
echo "▶ Installing pip dependencies (questionary, etc.)..."
if ! python3 -m pip install --user --break-system-packages -e .; then
    die "pip install failed. Check errors above and try again."
fi
if ! command -v nova &>/dev/null; then
    die "nova command not found after install. Ensure ~/.local/bin is on your PATH."
fi
step_ok "Nova CLI installed ($(nova version 2>/dev/null | tr -d '\n' || echo 'nova'))"

# ── 5. Shell hooks (nova install-hooks) ─────────────────────────────────────
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

# ── 7. Interactive setup (KB + AI) — first install only ─────────────────────
echo ""
if _nova_already_configured; then
    step_ok "Existing ~/.nova config found — setup skipped"
    echo ""
    echo "  You already have KB/AI settings. After git pull, use:"
    echo "    bash update.sh"
    echo "  To change settings:"
    echo "    nova setup"
else
    echo "▶ Running Nova setup (KB path + AI provider)..."
    echo ""
    if ! nova setup; then
        die "nova setup failed or was cancelled. Run 'nova setup' to try again."
    fi
    step_ok "Setup complete"
fi

# ── 7b. Optional Confluence (company knowledge search) ──────────────────────
_confluence_configured() {
    [[ -f "$HOME/.nova/confluence_config.json" ]] && [[ -f "$HOME/.nova/secrets.json" ]]
}

echo ""
if ! _confluence_configured; then
    read -r -p "Connect Confluence for company knowledge search? [y/N]: " connect_cf
    if [[ "${connect_cf:-}" =~ ^[Yy]$ ]]; then
        echo ""
        echo "  Atlassian API token: https://id.atlassian.com/manage-profile/security/api-tokens"
        if nova csetup; then
            step_ok "Confluence credentials saved"
            echo ""
            read -r -p "Sync Confluence spaces to a local index now? [y/N]: " do_sync
            if [[ "${do_sync:-}" =~ ^[Yy]$ ]]; then
                nova csync -r && step_ok "Confluence index ready" || \
                    echo "  ⚠  Sync skipped or failed — run  nova csync -r  later."
            fi
        else
            echo "  ⚠  Confluence setup skipped — run  nova csetup  later."
        fi
    fi
fi

# ── 8. Done ─────────────────────────────────────────────────────────────────
echo ""
echo " ✓ Nova installed successfully"
echo ""
echo " ┌─ Next steps ─────────────────────────────────────────────"
echo " │  1. Open a NEW terminal  (or run:  source ~/.bashrc)"
echo " │  2. Verify hooks:       echo \$NOVA_SESSION_DIR"
echo " │     → should print a path (empty = hooks not active)"
echo " │  3. Try error capture:"
echo " │       python3 -c \"import nosuchmodule\""
echo " │       nova up"
echo " │  4. Try company search:  nova ask i want to install kairos"
echo " │  5. Optional Confluence: nova csetup"
echo " └──────────────────────────────────────────────────────────"
echo ""
echo "  Updates:  bash update.sh   or   nova update --pull"
echo ""

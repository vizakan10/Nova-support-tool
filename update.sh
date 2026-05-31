#!/bin/bash
# Nova CLI — one-step update after git pull (keeps ~/.nova settings)
#
#   cd Nova-support-tool && bash update.sh
#
# Same as:  git pull --ff-only && nova update
# Reconfigure KB/AI:  bash update.sh --setup

set -euo pipefail

if [[ -n "${BASH_SOURCE[0]:-}" && "${BASH_SOURCE[0]}" != "bash" && -f "${BASH_SOURCE[0]}" ]]; then
    sed -i 's/\r//' "${BASH_SOURCE[0]}" 2>/dev/null \
        || sed -i '' 's/\r//' "${BASH_SOURCE[0]}" 2>/dev/null \
        || true
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

SETUP_AFTER=false
for arg in "$@"; do
    case "$arg" in
        --setup) SETUP_AFTER=true ;;
    esac
done

die() {
    echo ""
    echo "❌ $1" >&2
    echo ""
    exit 1
}

if [[ ! -f setup.py || ! -f nova_cli.py ]]; then
    die "Run this from the Nova-support-tool repo root."
fi

echo "╔══════════════════════════════════════════╗"
echo "║          🔄  Nova CLI — Update           ║"
echo "╚══════════════════════════════════════════╝"
echo ""

if [[ -d .git ]]; then
    echo "▶ git pull --ff-only ..."
    git pull --ff-only || die "git pull failed"
    echo "✅ Git pull OK"
else
    echo "⚠  Not a git repo — skipping pull"
fi

echo "▶ pip install -e . ..."
if ! python3 -m pip install --user --break-system-packages -e .; then
    python3 -m pip install --user -e . || die "pip install failed"
fi

export PATH="${HOME}/.local/bin:${PATH}"
if ! command -v nova &>/dev/null; then
    die "nova not on PATH. Run:  source ~/.bashrc"
fi

echo "▶ nova update ..."
if [[ "$SETUP_AFTER" == true ]]; then
    nova update --setup
else
    nova update
fi

echo ""
echo " ✓ Update complete (settings in ~/.nova are unchanged unless you used --setup)"
echo ""

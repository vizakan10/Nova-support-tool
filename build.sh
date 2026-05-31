#!/bin/bash
# Nova — build standalone binary
sed -i 's/\r//' "$0" 2>/dev/null || sed -i '' 's/\r//' "$0" 2>/dev/null || true

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Installing PyInstaller..."
python3 -m pip install pyinstaller --break-system-packages -q

echo "Building nova binary..."
python3 -m PyInstaller \
  --onefile \
  --name nova \
  --add-data "nova_hooks.sh:." \
  --add-data "nova_completion.sh:." \
  --hidden-import questionary \
  --hidden-import prompt_toolkit \
  --hidden-import config \
  --hidden-import kb_manager \
  --hidden-import confluence_manager \
  nova_cli.py

echo "✓ Binary built at dist/nova"
echo "  Size: $(du -sh dist/nova | cut -f1)"
echo ""
echo "Test it:"
echo "  ./dist/nova help"
echo ""
echo "To release: upload dist/nova to GitHub Releases"

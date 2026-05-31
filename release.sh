#!/bin/bash
sed -i 's/\r//' "$0" 2>/dev/null || sed -i '' 's/\r//' "$0" 2>/dev/null || true

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VERSION=$(grep version setup.py | head -1 | grep -o '[0-9.]*')
echo "Building nova v$VERSION..."

bash build.sh

echo ""
echo "Release checklist:"
echo "  1. Go to: https://github.com/vizakan10/Nova-support-tool/releases/new"
echo "  2. Tag: v$VERSION"
echo "  3. Upload: dist/nova"
echo "  4. Title: Nova v$VERSION"
echo "  5. Publish"
echo ""
echo "User install command will be:"
echo "  curl -L https://github.com/vizakan10/Nova-support-tool/releases/latest/download/nova -o nova && chmod +x nova && ./nova install-hooks"

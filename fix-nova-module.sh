#!/bin/bash
# One-time fix for "module 'nova' has no attribute 'main'" (name clash with other 'nova' packages).
# Run this inside the cloned Nova-support-tool folder, then reinstall.

set -e
cd "$(dirname "$0")"

if [ ! -f nova.py ] && [ ! -f nova_cli.py ]; then
  echo "Neither nova.py nor nova_cli.py found. Wrong directory?"
  exit 1
fi

if [ -f nova.py ] && [ ! -f nova_cli.py ]; then
  echo "Renaming nova.py -> nova_cli.py to avoid name clash..."
  cp nova.py nova_cli.py
  rm -f nova.py
fi

if grep -q 'nova=nova:main' setup.py 2>/dev/null; then
  echo "Updating setup.py to use nova_cli..."
  sed -i 's/"nova", "config", "kb_manager"/"nova_cli", "config", "kb_manager"/' setup.py
  sed -i 's/nova=nova:main/nova=nova_cli:main/' setup.py
fi

echo "Reinstalling Nova CLI..."
pip install --user --break-system-packages -e .

echo ""
echo "Done. Run:  nova setup"

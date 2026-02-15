#!/bin/bash
# Viza Installation Script for WSL

echo "=== Viza Installation ==="
echo ""

# Get the current directory
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Make the viza script executable
chmod +x "$INSTALL_DIR/viza"

# Check if ~/.local/bin exists, create if not
if [ ! -d "$HOME/.local/bin" ]; then
    mkdir -p "$HOME/.local/bin"
    echo "✓ Created ~/.local/bin directory"
fi

# Create symlink
ln -sf "$INSTALL_DIR/viza" "$HOME/.local/bin/viza"
echo "✓ Created symlink in ~/.local/bin"

# Check if ~/.local/bin is in PATH
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo ""
    echo "⚠️  ~/.local/bin is not in your PATH"
    echo "Add this line to your ~/.bashrc or ~/.zshrc:"
    echo ""
    echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""
    echo "Then run: source ~/.bashrc  (or source ~/.zshrc)"
else
    echo "✓ ~/.local/bin is already in PATH"
fi

echo ""
echo "=== Installation Complete ==="
echo "Usage: viza up"
echo ""

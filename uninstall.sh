#!/bin/bash
# Nova CLI — Uninstallation Script

echo "╔══════════════════════════════════════════╗"
echo "║         🗑️  Nova CLI Uninstaller         ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# 0. Require confirmation (password-style: user must type 'uninstall')
echo "⚠️  This will remove Nova CLI and optionally your config and PATH entry."
read -s -p "Type 'uninstall' to confirm: " confirm
echo ""
if [ "$confirm" != "uninstall" ]; then
    echo "❌ Confirmation failed. Exiting."
    exit 1
fi
echo ""

# 1. Uninstall the python package
echo "⚙️  Uninstalling Nova CLI package..."
# Use --break-system-packages for Ubuntu 24.04+ compatibility
python3 -m pip uninstall -y nova-cli --break-system-packages || echo "⚠️  Pip uninstall failed or package not found."

# 2. Cleanup entry point if pip missed it
if [ -f "$HOME/.local/bin/nova" ]; then
    rm "$HOME/.local/bin/nova"
    echo "✅ Removed entry point script."
fi

# 3. Ask to delete the config folder (~/.nova)
CONFIG_DIR="$HOME/.nova"
if [ -d "$CONFIG_DIR" ]; then
    read -p "❓ Delete configuration and secrets folder? ($CONFIG_DIR) [y/N]: " del_config
    if [[ $del_config =~ ^[Yy]$ ]]; then
        rm -rf "$CONFIG_DIR"
        echo "✅ Configuration deleted."
    else
        echo "ℹ️  Keeping configuration folder."
    fi
fi

# 3. Ask to remove PATH entry from .bashrc
BASHRC="$HOME/.bashrc"
if grep -q "# Nova CLI Path" "$BASHRC"; then
    read -p "❓ Remove Nova PATH entry from ~/.bashrc? [y/N]: " rem_path
    if [[ $rem_path =~ ^[Yy]$ ]]; then
        # Create a temp file without the Nova lines
        # This removes the comment and the export line following it
        sed -i '/# Nova CLI Path/,+1d' "$BASHRC"
        echo "✅ PATH entry removed from ~/.bashrc."
        echo "💡 Note: You may need to restart your terminal or run 'source ~/.bashrc'."
    else
        echo "ℹ️  Keeping PATH entry in ~/.bashrc."
    fi
fi

echo ""
echo "🎉 Nova CLI has been uninstalled."
echo ""

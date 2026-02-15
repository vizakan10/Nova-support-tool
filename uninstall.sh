#!/bin/bash
# Nova CLI — Uninstallation Script

echo "╔══════════════════════════════════════════╗"
echo "║         🗑️  Nova CLI Uninstaller         ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# 1. Uninstall the python package
echo "⚙️  Uninstalling Nova CLI package..."
python3 -m pip uninstall -y nova-cli || echo "⚠️  Package nova-cli not found or already uninstalled."

# 2. Ask to delete the config folder (~/.nova)
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

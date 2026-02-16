#!/bin/bash
# Nova CLI — Uninstallation Script
# You can run this from anywhere (no need to be inside the cloned repo).

echo "╔══════════════════════════════════════════╗"
echo "║         🗑️  Nova CLI Uninstaller         ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# 0. Require confirmation (password-style: user must type 'uninstall')
echo "⚠️  This will remove Nova CLI and optionally your config, PATH entry, and cloned folder."
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

# 4. Ask to remove PATH entry from .bashrc
BASHRC="$HOME/.bashrc"
if grep -q "# Nova CLI Path" "$BASHRC"; then
    read -p "❓ Remove Nova PATH entry from ~/.bashrc? [y/N]: " rem_path
    if [[ $rem_path =~ ^[Yy]$ ]]; then
        sed -i '/# Nova CLI Path/,+1d' "$BASHRC"
        echo "✅ PATH entry removed from ~/.bashrc."
        echo "💡 Note: You may need to restart your terminal or run 'source ~/.bashrc'."
    else
        echo "ℹ️  Keeping PATH entry in ~/.bashrc."
    fi
fi

# 5. Ask to remove cloned Nova-support-tool folder (if they installed via clone)
REPO_TO_REMOVE=""
if [ -f "install.sh" ] && [ -f "setup.py" ]; then
    read -p "❓ Remove this cloned folder (Nova-support-tool)? [y/N]: " del_repo
    if [[ $del_repo =~ ^[Yy]$ ]]; then
        REPO_TO_REMOVE="$(pwd)"
    fi
else
    read -p "❓ Remove a cloned Nova-support-tool folder? Enter its path (or Enter to skip): " repo_path
    repo_path="$(echo "$repo_path" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    if [ -n "$repo_path" ] && [ -d "$repo_path" ] && [ -f "$repo_path/install.sh" ]; then
        REPO_TO_REMOVE="$repo_path"
    fi
fi

echo ""
echo "🎉 Nova CLI has been uninstalled."
echo ""

if [ -n "$REPO_TO_REMOVE" ]; then
    echo "🗑️  Removing cloned folder: $REPO_TO_REMOVE"
    cd "$(dirname "$REPO_TO_REMOVE")" 2>/dev/null || true
    rm -rf "$REPO_TO_REMOVE"
    echo "✅ Folder removed."
    echo ""
fi

#!/bin/bash
# Nova CLI — Automatic Installation Script

set -e # Exit on error

echo "╔══════════════════════════════════════════╗"
echo "║          🚀  Nova CLI Installer          ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# 1. Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install it first."
    exit 1
fi

# 2. Check for apt and install dependencies
if command -v apt &> /dev/null; then
    echo "📦 Checking system dependencies (may require sudo)..."
    sudo apt update
    sudo apt install -y python3-pip python3-venv git
else
    echo "⚠️  Non-debian system detected. Please ensure pip and venv are installed manually."
fi

# 3. Install Nova locally
echo "⚙️  Installing Nova CLI..."
# We use --break-system-packages for Ubuntu 24.04+ compatibility when using --user
python3 -m pip install --user --break-system-packages -e .

# 4. PATH verification
LOCAL_BIN="$HOME/.local/bin"
if [[ ":$PATH:" != *":$LOCAL_BIN:"* ]]; then
    echo "⚠️  $LOCAL_BIN is not in your PATH."
    echo "🔧 Adding it to ~/.bashrc..."
    echo "" >> "$HOME/.bashrc"
    echo "# Nova CLI Path" >> "$HOME/.bashrc"
    echo "export PATH=\"\$HOME/.local/bin:\$PATH\"" >> "$HOME/.bashrc"
    
    # Export for the current session
    export PATH="$HOME/.local/bin:$PATH"
    echo "✅ PATH updated. Please run 'source ~/.bashrc' if 'nova' is not found."
else
    echo "✅ PATH is already configured."
fi

echo ""
echo "🎉 Installation complete!"
echo ""

# 5. Launch setup
read -p "❓ Would you like to run 'nova setup' now? [Y/n]: " run_setup
if [[ $run_setup =~ ^[Yy]?$ ]] || [[ -z $run_setup ]]; then
    nova setup
else
    echo "💡 You can run 'nova setup' anytime to configure the tool."
fi

# Viza - WSL Terminal Error Capture Tool

Capture and analyze terminal errors in WSL Ubuntu with a single command.

## Quick Install

### Option 1: Direct Install (Recommended)
```bash
# In WSL Ubuntu terminal
pip install --user git+https://github.com/yourusername/viza-wsl.git
```

### Option 2: From Downloaded Files
```bash
# Download and extract the package, then:
cd viza-wsl
pip install --user .
```

### Option 3: Development Mode
```bash
cd viza-wsl
pip install --user -e .
```

After installation, the `viza` command is available globally!

## Usage

### Capture Last Command Error
```bash
$ python3 script.py
Error: No such file or directory

$ viza up
✓ Error captured and saved to viza_context.txt!
```

### View Logs
```bash
$ viza log        # Last 5 entries
$ viza log 10     # Last 10 entries
```

### Get Help
```bash
$ viza help
```

## Example

```bash
# Try to run a command
$ python3 myapp.py
python3: command not found

# Capture it
$ viza up
📋 Capturing last terminal activity...

✓ Command: python3 myapp.py
✓ Success: No
✓ Return Code: 127
✓ Error Type: File Not Found

--- Error Output ---
bash: python3: command not found

✓ Full context saved to viza_context.txt
```

## What Gets Created

- `viza_context.txt` - Last error context (ready for LLM analysis)
- `wsl_terminal.log` - Full command history

## Uninstall

```bash
pip uninstall viza-wsl
```

## For Distribution

### As GitHub Repository
1. Push to GitHub
2. Users install: `pip install --user git+https://github.com/yourusername/viza-wsl.git`

### As ZIP Package
1. Zip the entire folder
2. Users extract and run: `pip install --user .`
3. Done! `viza` command works everywhere

## Requirements

- WSL Ubuntu (or any Linux)
- Python 3.6+
- pip (usually pre-installed)

## How It Works

1. Captures the last command from bash history
2. Re-executes it to get output and errors
3. Analyzes error types
4. Saves clean context for debugging or LLM analysis

No continuous monitoring, no background processes - just simple command execution when you need it!

# Nova CLI — Framework Reliability Agent

> Collaborative error resolution for development teams.  
> Search a shared Knowledge Base → AI fallback → zero-friction fixes.

## How It Works

```
  Error occurs → nova up → Search KB → Show fix
                               ↓ (no match)
                         AI suggests fix → Save to KB for the team
```

- **Knowledge Base** (`kb.json`) lives on SharePoint, synced via OneDrive
- **Tool** installed via pip from GitHub
- **No accounts, no dashboards** — just a CLI command

## Quick Install

### Method A: Direct (One-liner)
```bash
# In WSL / Linux terminal
pip install --user git+https://github.com/vizakan10/Nova-support-tool.git
nova setup
```

### Method B: Clone & Install (Recommended for WSL)
If you want to keep the source code or if `pip` is missing:
```bash
git clone https://github.com/vizakan10/Nova-support-tool.git
cd Nova-support-tool
chmod +x install.sh
./install.sh
```

## All Commands

### Error Resolution
| Command | Description |
|---------|-------------|
| `nova up` | Capture error → search KB → AI fallback |
| `nova add` | Save a new error solution to the KB |

### AI Provider Management
| Command | Description |
|---------|-------------|
| `nova add-llm` | Add a new AI provider (with nickname) |
| `nova rm <provider>` | Remove an AI provider |
| `nova use <provider>` | Switch active AI provider |
| `nova lp` | List all configured AI providers |
| `nova cur` | Show current active provider |
| `nova test [provider]` | Test connection to a provider |

### Configuration
| Command | Description |
|---------|-------------|
| `nova setup` | First-time config (KB path + AI) |
| `nova version` | Show version info |
| `nova secrets-path` | Show secrets file location |
| `nova help` | Show help message |

## Usage Examples

### `nova up` — Error Intercept

```bash
# Auto-capture from terminal
$ nova up

# Or pipe errors directly
$ python3 app.py 2>&1 | nova up
```

**What happens:**
1. Scans last terminal output for error patterns
2. If no error detected → prompts you to paste it (Ctrl+D to submit)
3. Fuzzy-searches the team's KB (≥70% match)
4. If no KB match → asks AI (if configured)
5. Shows solution + command, asks permission to run

### `nova add` — Knowledge Capture

```bash
$ nova add

  Error signature: ModuleNotFoundError: No module named 'requests'
  Solution (1 sentence): Install the missing Python package.
  Fix command (optional, Enter to skip):    ← can leave empty

  🔒 Sanitizing...
  ✅ Entry saved to KB!
```

**Mandatory fields:** Error signature, Solution  
**Optional field:** Fix command (press Enter to skip)

Sensitive data (IPs, API keys, paths) is **automatically redacted** before saving.

### `nova add-llm` — Add AI Provider

```bash
$ nova add-llm

? 🤖 Choose AI provider:
  ❯ groq
    openai
    claude

? 🔑 API key: ****

? 📦 Model:
  ❯ llama-3.1-8b-instant

? 🏷  Nickname: groq-llam

  ✅ Provider 'groq-llam' added and set as active.
```

### `nova lp` — List Providers

```bash
$ nova lp

  🤖 Configured AI Providers

  ● active  groq-llam   (groq/llama-3.1-8b-instant)
  ○         openai-gpt4 (openai/gpt-4o)
```

### `nova use <provider>` — Switch Provider

```bash
$ nova use openai-gpt4
  ✅ Active provider set to 'openai-gpt4' (openai/gpt-4o)
```

## Configuration Storage

```
~/.nova/
├── config.json       # KB path, username, active provider
├── providers.json    # All provider configs {nickname: {provider, model, endpoint}}
└── secrets.json      # API keys {nickname: key}  (kept separate for safety)
```

## KB Schema (`kb.json`)

```json
[
  {
    "error": "ModuleNotFoundError: No module named 'requests'",
    "solution": "Install the missing Python package using pip.",
    "command": "pip install requests",
    "added_by": "visat",
    "timestamp": "2026-02-15T21:00:00+00:00"
  }
]
```

## OneDrive Sync

```
SharePoint:  Company SharePoint → Nova-KB → kb.json
                    ↕ (OneDrive auto-sync)
Local:       /mnt/c/Users/you/OneDrive - Company/Nova-KB/kb.json
                    ↕ (Nova reads/writes)
```

OneDrive conflict copies (`kb-DESKTOP-123.json`) are **auto-detected and merged**.

## Safety & Privacy

- API keys, tokens, passwords → `[KEY_REDACTED]`
- IP addresses → `[IP_REDACTED]`
- User paths → `C:\Users\[USER]`
- Long tokens → `[DATA_REDACTED]`
- Email addresses → `[EMAIL_REDACTED]`

## Requirements

- Python 3.8+
- WSL / Linux
- OneDrive desktop sync (for KB access)
- `questionary` (auto-installed via pip)
- AI provider API key (optional)

## License

MIT

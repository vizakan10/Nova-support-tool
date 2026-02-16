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

**If you see** `AttributeError: module 'nova' has no attribute 'main'` **(name clash with another package), run this once in the clone then run `nova setup` again:**
```bash
cd Nova-support-tool
cp nova.py nova_cli.py && rm -f nova.py
sed -i 's/"nova", "config", "kb_manager"/"nova_cli", "config", "kb_manager"/' setup.py
sed -i 's/nova=nova:main/nova=nova_cli:main/' setup.py
pip install --user --break-system-packages -e .
```

## All Commands

Run **`nova help`** to see the full command list and **Active Environment** (Config path, KB file path, Secrets path, AI host).

### Support
| Command | Description |
|---------|-------------|
| `nova up` | Solve last terminal error (KB → AI) |
| `nova fix` | Paste error and get instant solution |
| `nova ask` / `nova -a [question]` | Ask Nova AI a direct question |
| `nova solve` | Review history and add a custom fix |
| `nova log [n]` | Show last n terminal entries |

### Knowledge (KB = kb.json)
| Command | Description |
|---------|-------------|
| `nova add` | Manually add one error pattern |
| `nova kb list` | List all solutions (table with ID) |
| `nova kb rm <ID>` | Delete solution by table ID |
| `nova kb search [query]` | Manual lookup test |
| `nova kb path [path]` | View or update KB storage path |
| `nova add-kb <nick> <path>` | Register a new KB folder |
| `nova rm-kb <nick>` / `nova use-kb <nick>` | Unlink or switch KB |
| `nova lk` / `nova cur-kb` | List KBs, show current |

### AI / LLM
| Command | Description |
|---------|-------------|
| `nova save <nick>` | Save current LLM setup as profile |
| `nova use <nick>` | Switch to saved profile |
| `nova providers` | List supported AI hosts |
| `nova set-provider` | Change AI host (interactive) |
| `nova model <m>` | Update model for active provider |
| `nova apikey [k]` | Save provider API key securely |
| `nova add-llm` | Add new AI provider |
| `nova rm <nick>` / `nova lp` / `nova cur` / `nova test` | Remove, list, current, test |

### System
| Command | Description |
|---------|-------------|
| `nova list` | Show all paths and profile nicknames |
| `nova init` | Run configuration wizard (alias: setup) |
| `nova config` | Show full config + Active Environment |
| `nova fresh` | Wipe all settings and restart |
| `nova version` / `nova secrets-path` / `nova help` | Version, secrets path, help |

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
├── secrets.json      # API keys {nickname: key}  (kept separate for safety)
└── announce_state.json  # Last daily announcements check (used silently)
```

## Announcements

**Simple:** You push updates to `announcements.json` → next day when users run `nova`, they see it. No push → nothing new.

On the first run of any `nova` command each day, Nova fetches `announcements.json` from the repo. New announcements (new `id`) are shown once. To announce something:

1. Edit **`announcements.json`** in the repo (same format as below).
2. Push to the default branch (`main` or `master`).
3. Users get new announcements the next time they run `nova` on a new day.

```json
{
  "announcements": [
    {
      "id": "unique-id-20260216",
      "date": "2026-02-16",
      "title": "Your title",
      "body": "Message body. Can be multiple lines."
    }
  ]
}
```

Each announcement needs a unique `id`; users won’t see the same one twice.

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

## Uninstallation

To completely remove Nova CLI and all its data:

```bash
chmod +x uninstall.sh
./uninstall.sh
```

**Security:** The uninstaller asks you to type **`uninstall`** to confirm before removing anything.

## Requirements

- Python 3.8+
- WSL / Linux
- OneDrive desktop sync (for KB access)
- `questionary` (auto-installed via pip)
- AI provider API key (optional)

## License

MIT

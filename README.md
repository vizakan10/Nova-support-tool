# Nova CLI — Framework Reliability Agent

> Collaborative error resolution for development teams.  
> Search a shared Knowledge Base → AI fallback → zero-friction fixes.

## How It Works

```
  Error occurs → nova up → KB → Confluence → AI
                               ↓ (no match)
                         AI suggests fix → Save to KB for the team
```

- **Knowledge Base** (`kb.json`) lives on SharePoint, synced via OneDrive
- **Tool** installed via pip from GitHub
- **No accounts, no dashboards** — just a CLI command

## Quick Install

### One command (recommended)

From anywhere (WSL / Linux) — clones, installs pip package, hooks, and runs `nova setup`:

```bash
curl -fsSL https://raw.githubusercontent.com/vizakan10/Nova-support-tool/main/install.sh | bash
```

Already cloned the repo? No `chmod` needed:

```bash
cd Nova-support-tool
bash install.sh
```

After install, if `nova up` says hooks are not loaded in this terminal, run once:

```bash
source ~/.bashrc
```

(or open a new terminal — hooks load automatically there.)

### Update after `git pull` (no uninstall)

Your `~/.nova` settings (KB path, AI keys, providers) are **kept**. One command from the repo:

```bash
cd Nova-support-tool
git pull
bash update.sh
```

Or from anywhere (if Nova is already installed):

```bash
cd Nova-support-tool
nova update --pull
```

Refresh hooks in this terminal if needed: `source ~/.bashrc`

To change KB or AI settings after an update: `nova update --setup` or `bash update.sh --setup`

### Pip only (minimal)

```bash
pip install --user git+https://github.com/vizakan10/Nova-support-tool.git
nova setup
nova install-hooks
source ~/.bashrc
```

kb cloud - https://ifs-my.sharepoint.com/:f:/p/thangaratnam_visakan/IgAck2Z76LdFS5qlRgJ-x2jfAVg8dkVAdlavUg8XG0F-FnA?e=VUPQqB

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
| `nova up` | Last terminal error (KB → Confluence → AI) |
| `nova search [q]` | KB first, then AI |
| `nova ask` / `nova -a [question]` | Direct AI question (no KB) |

### Knowledge (KB = kb.json)
| Command | Description |
|---------|-------------|
| `nova add` | Add one error/solution to KB |
| `nova kb list` | List KB entries (with ID) |
| `nova kb rm <ID>` | Delete entry by ID |
| `nova kb path [path]` | View or change KB folder |
| `nova add-kb` / `use-kb` / `rm-kb` | Extra KB sources |

### AI / LLM
| Command | Description |
|---------|-------------|
| `nova setup` | Configure KB + AI (wizard) |
| `nova add-llm` | Add AI provider |
| `nova use <nick>` | Switch AI profile |
| `nova set-provider` | Pick profile (interactive) |
| `nova model <m>` / `nova apikey [k]` | Model / API key |
| `nova test` | Test AI connection |
| `nova rm <nick>` | Remove AI profile |

### System
| Command | Description |
|---------|-------------|
| `nova list` | KB paths + AI profiles |
| `nova config` | Active config + paths |
| `nova update --pull` | After `git pull` (keeps settings) |
| `nova ano` | Announcements |
| `nova fresh` | Wipe settings |
| `nova help` / `nova version` | Help / version |

Old names (`init`, `fix`, `lp`, `lk`, …) still auto-redirect with a short notice.

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

### `nova list` — Paths and profiles

```bash
$ nova list

  Knowledge Bases:
  ● main  /path/to/Nova-KB
  AI Profiles:
  ● groq-llam  (groq/llama-3.1-8b-instant)
```

### `nova use <provider>` — Switch Provider

```bash
$ nova use openai-gpt4
  ✅ Active provider set to 'openai-gpt4' (openai/gpt-4o)
```

## Tests

Offline unit tests (no API keys or network):

```bash
python3 -m unittest discover -s tests -v
# or
bash run_tests.sh
```

Covers Confluence RAG scoring/ranking, `Basic` auth header, KB fuzzy search, and `nova ask` answer polish.

## Configuration Storage

```
~/.nova/
├── config.json       # KB path, username, active provider
├── providers.json    # All provider configs {nickname: {provider, model, endpoint}}
├── secrets.json      # API keys {nickname: key}  (kept separate for safety)
└── announce_state.json  # Last daily announcements check (used silently)
```

## Announcements

**Simple:** You push updates to `announcements.json` → next day when users run `nova`, they see it. No push → nothing new. Users can run **`nova ano`** anytime to fetch and view the latest announcements.

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

One command from anywhere:

```bash
curl -fsSL https://raw.githubusercontent.com/vizakan10/Nova-support-tool/main/uninstall.sh | bash
```

Or from a clone (no `chmod` needed):

```bash
bash uninstall.sh
# or: bash /path/to/Nova-support-tool/uninstall.sh
```

The script will:
1. Ask you to type **`uninstall`** to confirm.
2. Uninstall the package and remove the `nova` script.
3. Optionally delete `~/.nova` (config and secrets).
4. Optionally remove the Nova PATH line from `~/.bashrc`.
5. Optionally **remove the cloned Nova-support-tool folder** (if you run from inside it, or if you enter its path when asked).

## Requirements

- Python 3.8+
- WSL / Linux
- OneDrive desktop sync (for KB access)
- `questionary` (auto-installed via pip)
- AI provider API key (optional)

## License

MIT

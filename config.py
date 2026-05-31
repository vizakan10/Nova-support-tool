#!/usr/bin/env python3
"""
Nova CLI — Configuration Manager
Multi-provider AI support, secrets management, multi-KB sources, interactive setup.
"""

import os
import re
import json
import getpass

# ─── Paths ───────────────────────────────────────────────────────────────────
CONFIG_DIR = os.path.expanduser("~/.nova")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
PROVIDERS_FILE = os.path.join(CONFIG_DIR, "providers.json")
SECRETS_FILE = os.path.join(CONFIG_DIR, "secrets.json")
KBS_FILE = os.path.join(CONFIG_DIR, "kb_sources.json")

# Default urllib User-Agent (Python-urllib/3.x) is often blocked by CDN/WAF rules
# in front of LLM APIs (e.g. Cloudflare 1010 / "browser signature").
NOVA_HTTP_USER_AGENT = "Nova-CLI/2.0.0"

# ─── API key / token URLs (shown during setup) ───────────────────────────────
ATLASSIAN_API_TOKEN_URL = (
    "https://id.atlassian.com/manage-profile/security/api-tokens"
)

# ─── AI Provider Defaults ────────────────────────────────────────────────────
AI_PROVIDERS = {
    "groq": {
        "endpoint": "https://api.groq.com/openai/v1/chat/completions",
        "models": [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "mixtral-8x7b-32768",
            "Other",
        ],
        "key_url": "https://console.groq.com/keys",
        "key_hint": "Free tier — create an API key in Groq Console",
    },
    "openai": {
        "endpoint": "https://api.openai.com/v1/chat/completions",
        "models": ["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo", "Other"],
        "key_url": "https://platform.openai.com/api-keys",
        "key_hint": "Requires an OpenAI account with billing or credits",
    },
    "claude": {
        "endpoint": "https://api.anthropic.com/v1/messages",
        "models": [
            "claude-3-5-sonnet-20241022",
            "claude-3-opus-20240229",
            "Other",
        ],
        "key_url": "https://console.anthropic.com/settings/keys",
        "key_hint": "Anthropic API key (Claude)",
    },
    "deepseek": {
        "endpoint": "https://api.deepseek.com/v1/chat/completions",
        "models": ["deepseek-chat", "deepseek-coder", "Other"],
        "key_url": "https://platform.deepseek.com/api_keys",
        "key_hint": "DeepSeek platform API key",
    },
    "ollama": {
        "endpoint": "http://localhost:11434/v1/chat/completions",
        "models": ["llama3", "mistral", "codellama", "Other"],
        "key_url": "https://ollama.com/download",
        "key_hint": "Local only — install Ollama; use any placeholder for API key",
    },
    "google": {
        "endpoint": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "models": ["gemini-2.0-flash", "gemini-1.5-pro", "Other"],
        "key_url": "https://aistudio.google.com/apikey",
        "key_hint": "Google AI Studio API key (Gemini)",
    },
}


def get_provider_key_url(provider_type):
    """URL where the user can create an API key for *provider_type*."""
    info = AI_PROVIDERS.get(provider_type) or {}
    return (info.get("key_url") or "").strip()


def print_provider_key_help(provider_type, *, prefix="  "):
    """Print where to get an API key before prompting."""
    info = AI_PROVIDERS.get(provider_type) or {}
    url = (info.get("key_url") or "").strip()
    hint = (info.get("key_hint") or "").strip()
    if url:
        print(f"{prefix}Get API key: {url}")
    if hint:
        print(f"{prefix}{hint}")
    if url or hint:
        print()


# ═══════════════════════════════════════════════════════════════════════════════
#  FILE I/O
# ═══════════════════════════════════════════════════════════════════════════════

def _ensure_dir():
    os.makedirs(CONFIG_DIR, exist_ok=True)


def _normalize_kb_path(path):
    """
    When running on Linux/WSL, convert Windows paths to /mnt/... so they work.
    Users can paste C:\\Users\\... or C:/... and we store the path that works.
    """
    path = str(path).strip().strip('"\'').replace("\\", "/")
    if not path:
        return path
    path = os.path.expanduser(path)
    # On Linux/WSL: C:\ or C:/ -> /mnt/c/
    if os.name != "nt" and len(path) >= 2 and path[1] == ":" and path[0].upper().isalpha():
        drive = path[0].lower()
        path = "/mnt/" + drive + path[2:]
    return path


def normalize_kb_path(path):
    """Public helper: normalize a KB path (Windows -> /mnt when on WSL)."""
    return _normalize_kb_path(path)


def _load_json(path, default=None):
    if default is None:
        default = {}
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(default, dict) and not isinstance(data, dict):
            return default
        return data
    except (json.JSONDecodeError, IOError, OSError):
        return default


def _save_json(path, data):
    _ensure_dir()
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


# ── config.json ──────────────────────────────────────────────────────────────
def load_config():
    """Load core config (active_kb, added_by, active_provider)."""
    cfg = _load_json(CONFIG_FILE)
    if not cfg or not isinstance(cfg, dict):
        return None
    
    # Migration: if old 'kb_path' exists but no 'active_kb'
    if "kb_path" in cfg and "active_kb" not in cfg:
        path = cfg.pop("kb_path")
        _ensure_dir()
        kbs = load_kbs()
        if "main" not in kbs:
            kbs["main"] = path
            save_kbs(kbs)
        cfg["active_kb"] = "main"
        save_config(cfg)
        
    return cfg


def save_config(config):
    _save_json(CONFIG_FILE, config)


# ── providers.json ───────────────────────────────────────────────────────────
def load_providers():
    """Load all saved providers as {nickname: {provider, model, endpoint}}."""
    return _load_json(PROVIDERS_FILE, {})


def save_providers(providers):
    _save_json(PROVIDERS_FILE, providers)


# ── secrets.json ─────────────────────────────────────────────────────────────
def load_secrets():
    """Load API keys as {nickname: key}."""
    return _load_json(SECRETS_FILE, {})


def save_secrets(secrets):
    _save_json(SECRETS_FILE, secrets)


# ── kb_sources.json ─────────────────────────────────────────────────────────
def load_kbs():
    """Load all saved KB folders as {nickname: path}."""
    return _load_json(KBS_FILE, {})


def save_kbs(kbs):
    _save_json(KBS_FILE, kbs)


# ═══════════════════════════════════════════════════════════════════════════════
#  KB MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

def add_kb_source(nickname, path):
    """Register a new Knowledge Base folder. Normalizes Windows -> /mnt when on WSL."""
    if not path or (isinstance(path, str) and not path.strip()):
        return
    path = _normalize_kb_path(path)
    if not path:
        return
    kbs = load_kbs()
    kbs[nickname] = os.path.abspath(path) if path else path
    save_kbs(kbs)
    _ensure_kb_file(kbs[nickname])


def remove_kb_source(nickname):
    """Remove a KB source by nickname."""
    kbs = load_kbs()
    if nickname not in kbs:
        return False
    
    del kbs[nickname]
    save_kbs(kbs)
    
    cfg = load_config()
    if cfg and cfg.get("active_kb") == nickname:
        cfg["active_kb"] = ""
        save_config(cfg)
    return True


def switch_kb(nickname):
    """Set the active KB source."""
    kbs = load_kbs()
    if nickname not in kbs:
        return False
    
    cfg = load_config()
    if not cfg:
        cfg = {"added_by": getpass.getuser(), "active_provider": "", "active_kb": ""}
    
    cfg["active_kb"] = nickname
    save_config(cfg)
    return True


def get_active_kb_path():
    """Return the absolute path of the current active KB."""
    cfg = load_config()
    if not cfg:
        return None
    
    active = cfg.get("active_kb", "")
    if not active:
        return None
    
    kbs = load_kbs()
    return kbs.get(active)


def ensure_active_kb_ready():
    """Return active KB path, creating the folder and kb.json if missing (no crash)."""
    cfg = load_config()
    if not cfg or not cfg.get("active_kb"):
        return None
    kb_path = get_active_kb_path()
    if not kb_path:
        return None
    try:
        os.makedirs(kb_path, exist_ok=True)
        kb_file = os.path.join(kb_path, "kb.json")
        if not os.path.isfile(kb_file):
            with open(kb_file, "w", encoding="utf-8") as fh:
                json.dump([], fh, indent=2)
        return kb_path
    except OSError:
        return None


def list_all_kbs():
    """Return list of (nickname, path, is_active) tuples."""
    cfg = load_config() or {}
    active = cfg.get("active_kb", "")
    kbs = load_kbs()
    
    items = []
    for nick, path in kbs.items():
        items.append((nick, path, nick == active))
    return items


# ═══════════════════════════════════════════════════════════════════════════════
#  AI PROVIDER MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

def add_provider(nickname, provider_type, model, endpoint, api_key):
    """Register a new AI provider under *nickname*."""
    nickname = (nickname or "").strip() if nickname is not None else ""
    if not nickname:
        return
    model = (model or "").strip() if model is not None else ""
    endpoint = (endpoint or "").strip() if endpoint is not None else ""
    api_key = api_key if api_key is not None else ""
    providers = load_providers()
    secrets = load_secrets()

    providers[nickname] = {
        "provider": (provider_type or "").strip() if provider_type else "",
        "model": model,
        "endpoint": endpoint or (AI_PROVIDERS.get(provider_type, {}) or {}).get("endpoint", ""),
    }
    secrets[nickname] = api_key

    save_providers(providers)
    save_secrets(secrets)


def remove_provider(nickname):
    """Remove a provider by nickname. Returns True if found."""
    providers = load_providers()
    secrets = load_secrets()

    if nickname not in providers:
        return False

    del providers[nickname]
    secrets.pop(nickname, None)

    save_providers(providers)
    save_secrets(secrets)

    # If it was the active provider, clear it
    cfg = load_config()
    if cfg and cfg.get("active_provider") == nickname:
        cfg["active_provider"] = ""
        save_config(cfg)

    return True


def switch_provider(nickname):
    """Set *nickname* as the active AI provider. Returns True if valid."""
    providers = load_providers()
    if nickname not in providers:
        return False

    cfg = load_config()
    if not cfg:
        cfg = {"added_by": getpass.getuser(), "active_provider": "", "active_kb": ""}
    cfg["active_provider"] = nickname
    save_config(cfg)
    return True


def save_current_as_profile(nickname):
    """Save the current LLM setup as a new profile (clone under new nickname). Returns True if success."""
    info = get_active_ai_config()
    if not info or not nickname.strip():
        return False
    add_provider(
        nickname.strip(),
        info.get("provider", ""),
        info.get("model", ""),
        info.get("endpoint", ""),
        info.get("api_key", ""),
    )
    return True


def get_active_ai_config():
    """
    Return the active provider's full config dict for use by nova up.
    """
    cfg = load_config()
    if not cfg:
        return None

    active = cfg.get("active_provider", "")
    if not active:
        return None

    providers = load_providers()
    secrets = load_secrets()

    if active not in providers:
        return None

    info = providers[active].copy()
    info["api_key"] = secrets.get(active, "")
    return info


def list_all_providers():
    """Return list of (nickname, info_dict, is_active) tuples."""
    cfg = load_config() or {}
    active = cfg.get("active_provider", "")
    providers = load_providers()

    result = []
    for nick, info in providers.items():
        result.append((nick, info, nick == active))
    return result


def _generate_nickname(provider_type, model, existing_providers):
    """Auto-generate a nickname like 'groq-llam' and deduplicate."""
    base = f"{provider_type}-{model[:4].lower()}"
    nick = base
    seq = 1
    while nick in existing_providers:
        nick = f"{base}-{seq}"
        seq += 1
    return nick


# ═══════════════════════════════════════════════════════════════════════════════
#  INTERACTIVE SETUP (first-time)
# ═══════════════════════════════════════════════════════════════════════════════

_SETUP_BACK_LABEL = "0 ← Back"
_SETUP_BACK_HINT = "Type 0 to go back"


def interactive_setup():
    """First-time setup wizard."""
    try:
        import questionary
        return _setup_rich(questionary)
    except ImportError:
        print("\n  ⚠  'questionary' not installed — using basic prompts.\n")
        return _setup_basic()


def _get_style(q):
    return q.Style([
        ("qmark", "fg:#36a3ff bold"),
        ("question", "bold"),
        ("answer", "fg:#36a3ff bold"),
        ("pointer", "fg:#0055ff bold"),
        ("highlighted", "fg:#0055ff bold"),
        ("instruction", "fg:#888888 italic"),
    ])


def _setup_input_is_back(value):
    return str(value or "").strip() == "0"


def _parse_kb_path_input(raw):
    """
    Normalize and validate KB path input.
    Returns (True, path) or (False, error_message).
    """
    kb_path = raw.strip().strip('"\'').replace("\n", " ").replace("\r", " ").strip()
    kb_path = re.sub(
        r"\s+[\\/]?\s*kb\.json\s*$", "/kb.json", kb_path, flags=re.IGNORECASE
    ).strip()
    if not kb_path:
        return False, "   ❌ KB path cannot be empty."

    if kb_path.rstrip().endswith("kb.json"):
        _dir = os.path.dirname(os.path.normpath(kb_path.rstrip()))
        if _dir:
            kb_path = _dir

    kb_path = _normalize_kb_path(kb_path)

    if kb_path and (os.path.isfile(kb_path) or kb_path.rstrip().endswith("kb.json")):
        _dir = os.path.dirname(os.path.normpath(kb_path.rstrip()))
        if _dir:
            kb_path = _dir
    kb_path = (kb_path or "").rstrip().rstrip("/")

    if not kb_path:
        return False, (
            "   ❌ KB path is empty or invalid (e.g. only 'kb.json' was entered). "
            "Please enter the folder path."
        )
    if os.path.basename(kb_path.rstrip("/")) == "kb.json":
        return False, (
            "   ❌ Please enter the folder that contains kb.json, "
            "not the file path."
        )
    return True, kb_path


def _commit_kb_main(kb_path):
    _ensure_kb_file(kb_path)
    add_kb_source("main", kb_path)
    cfg = load_config() or {}
    cfg["active_kb"] = "main"
    cfg["added_by"] = getpass.getuser()
    save_config(cfg)


def _setup_print_header():
    print("\n╔══════════════════════════════════════════╗")
    print("║        🚀  Nova CLI — First Setup        ║")
    print("╚══════════════════════════════════════════╝")
    print(f"  {_SETUP_BACK_HINT} on any step (0 on first step = cancel)\n")


def _setup_rich_select_with_back(q, message, choices, style):
    """questionary select; first choice is Back. Returns choice, 'BACK', or None (cancel)."""
    full = [_SETUP_BACK_LABEL] + list(choices)
    picked = q.select(message, choices=full, style=style).ask()
    if picked is None:
        return None
    if picked == _SETUP_BACK_LABEL or _setup_input_is_back(picked):
        return "BACK"
    return picked


def _setup_rich(q):
    style = _get_style(q)
    _setup_print_header()

    step = 0
    kb_path = None
    p_type = None
    api_key = model = endpoint = nickname = None

    while True:
        if step == 0:
            kb_path = q.text(
                "📁 KB folder path (or path to kb.json):",
                instruction=(
                    "e.g. /mnt/c/Users/you/OneDrive/Nova-KB  —  "
                    f"{_SETUP_BACK_HINT} (cancel setup)"
                ),
                style=style,
            ).ask()
            if kb_path is None:
                return None
            if _setup_input_is_back(kb_path):
                print("   Setup cancelled.")
                return None
            ok, result = _parse_kb_path_input(kb_path)
            if not ok:
                print(result)
                continue
            kb_path = result
            if not os.path.isdir(kb_path):
                step = 1
            else:
                _commit_kb_main(kb_path)
                step = 2

        elif step == 1:
            picked = _setup_rich_select_with_back(
                q,
                f"   '{kb_path}' doesn't exist. Create it?",
                ["Yes, create folder", "No, re-enter path"],
                style,
            )
            if picked is None:
                return None
            if picked == "BACK":
                step = 0
                continue
            if picked == "No, re-enter path":
                step = 0
                continue
            if os.path.isfile(kb_path):
                kb_path = os.path.dirname(kb_path)
            if not kb_path:
                print("   ❌ Cannot create: path is invalid.")
                step = 0
                continue
            os.makedirs(kb_path, exist_ok=True)
            _commit_kb_main(kb_path)
            step = 2

        elif step == 2:
            provider_choices = list(AI_PROVIDERS.keys()) + ["Skip (no AI)"]
            p_type = _setup_rich_select_with_back(
                q,
                "🤖 Choose AI provider (optional):",
                provider_choices,
                style,
            )
            if p_type is None:
                return None
            if p_type == "BACK":
                step = 0
                continue
            if p_type == "Skip (no AI)":
                cfg = load_config() or {}
                _print_summary(cfg)
                return cfg
            step = 3

        elif step == 3:
            print_provider_key_help(p_type)
            api_key = q.password(
                "🔑 API key:",
                instruction=_SETUP_BACK_HINT,
                style=style,
            ).ask()
            if api_key is None:
                return None
            if _setup_input_is_back(api_key):
                step = 2
                continue
            if not api_key:
                print("   ❌ API key cannot be empty.")
                continue
            step = 4

        elif step == 4:
            models = AI_PROVIDERS[p_type]["models"]
            model = _setup_rich_select_with_back(
                q, "📦 Model:", models, style
            )
            if model is None:
                return None
            if model == "BACK":
                step = 3
                continue
            step = 5

        elif step == 5:
            default_ep = AI_PROVIDERS[p_type]["endpoint"]
            endpoint = q.text(
                "🌐 Endpoint:",
                default=default_ep,
                instruction=_SETUP_BACK_HINT,
                style=style,
            ).ask()
            if endpoint is None:
                return None
            if _setup_input_is_back(endpoint):
                step = 4
                continue
            endpoint = endpoint or default_ep
            step = 6

        elif step == 6:
            existing = load_providers()
            default_nick = _generate_nickname(p_type, model, existing)
            nickname = q.text(
                "🏷  Nickname:",
                default=default_nick,
                instruction=_SETUP_BACK_HINT,
                style=style,
            ).ask()
            if nickname is None:
                return None
            if _setup_input_is_back(nickname):
                step = 5
                continue
            nickname = nickname or default_nick
            add_provider(nickname, p_type, model, endpoint, api_key)
            cfg = load_config() or {}
            cfg["active_provider"] = nickname
            save_config(cfg)
            _print_summary(cfg)
            return cfg


def _setup_basic_read(prompt, *, allow_back=True):
    """Read a line; return BACK sentinel, None on EOF, or stripped value."""
    hint = f" ({_SETUP_BACK_HINT})" if allow_back else " (0 = cancel)"
    try:
        value = input(f"{prompt}{hint}: ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    if allow_back and _setup_input_is_back(value):
        return "BACK"
    if not allow_back and _setup_input_is_back(value):
        print("   Setup cancelled.")
        return None
    return value


def _setup_basic():
    print("\n══════════════════════════════════════════")
    print("        🚀  Nova CLI — First Setup")
    print("══════════════════════════════════════════")
    print(f"  {_SETUP_BACK_HINT} (0 on first step = cancel)\n")

    step = 0
    kb_path = None
    p_type = None

    while True:
        if step == 0:
            raw = _setup_basic_read(
                "📁 KB folder path (or path to kb.json)",
                allow_back=False,
            )
            if raw is None:
                return None
            ok, result = _parse_kb_path_input(raw)
            if not ok:
                print(result)
                continue
            kb_path = result
            if not os.path.isdir(kb_path):
                step = 1
            else:
                _commit_kb_main(kb_path)
                step = 2

        elif step == 1:
            yn = _setup_basic_read(
                f"   '{kb_path}' doesn't exist. Create? [Y/n/0]",
                allow_back=True,
            )
            if yn is None:
                return None
            if yn == "BACK":
                step = 0
                continue
            if yn.lower() in ("", "y", "yes"):
                if os.path.isfile(kb_path):
                    kb_path = os.path.dirname(kb_path)
                if kb_path:
                    os.makedirs(kb_path, exist_ok=True)
                _commit_kb_main(kb_path)
                step = 2
            else:
                step = 0

        elif step == 2:
            plist = list(AI_PROVIDERS.keys())
            print("\n  Available AI providers:")
            print(f"    0. {_SETUP_BACK_LABEL}")
            for i, p in enumerate(plist, 1):
                url = get_provider_key_url(p)
                if url:
                    print(f"    {i}. {p}  →  {url}")
                else:
                    print(f"    {i}. {p}")
            print(f"    {len(plist) + 1}. Skip (no AI)")
            try:
                choice = input(
                    f"  Choose [0-{len(plist) + 1}]: "
                ).strip()
            except (EOFError, KeyboardInterrupt):
                return None
            if _setup_input_is_back(choice):
                step = 0
                continue
            try:
                idx = int(choice) - 1
            except ValueError:
                print("   ❌ Enter a number from the list.")
                continue
            if idx < 0 or idx > len(plist):
                print("   ❌ Enter a number from the list.")
                continue
            if idx == len(plist):
                cfg = load_config() or {}
                _print_summary(cfg)
                return cfg
            p_type = plist[idx]
            step = 3

        elif step == 3:
            result = _add_provider_basic(p_type, set_active=True, allow_back=True)
            if result == "BACK":
                step = 2
                continue
            if result is None:
                return None
            cfg = load_config() or {}
            _print_summary(cfg)
            return cfg


def add_provider_interactive(p_type=None):
    try:
        import questionary
        q = questionary
        style = _get_style(q)
        if p_type is None:
            p_type = q.select("🤖 Choose AI provider:", choices=list(AI_PROVIDERS.keys()), style=style).ask()
        if not p_type: return None
        return _add_provider_rich(q, style, p_type, set_active=True)
    except ImportError:
        if p_type is None:
            plist = list(AI_PROVIDERS.keys())
            for i, p in enumerate(plist, 1):
                url = get_provider_key_url(p)
                if url:
                    print(f"    {i}. {p}  →  {url}")
                else:
                    print(f"    {i}. {p}")
            try:
                c = int(input(f"  Choose [1-{len(plist)}]: ").strip()) - 1
                p_type = plist[c]
            except: return None
        return _add_provider_basic(p_type, set_active=True)


def _add_provider_rich(q, style, p_type, set_active=False):
    print_provider_key_help(p_type)
    api_key = q.password("🔑 API key:", style=style).ask()
    if not api_key: return None
    
    models = AI_PROVIDERS[p_type]["models"]
    model = q.select("📦 Model:", choices=models, style=style).ask()
    default_ep = AI_PROVIDERS[p_type]["endpoint"]
    endpoint = q.text("🌐 Endpoint:", default=default_ep, style=style).ask() or default_ep

    existing = load_providers()
    default_nick = _generate_nickname(p_type, model, existing)
    nickname = q.text("🏷  Nickname:", default=default_nick, style=style).ask() or default_nick

    add_provider(nickname, p_type, model, endpoint, api_key)
    if set_active:
        cfg = load_config() or {}
        cfg["active_provider"] = nickname
        save_config(cfg)
    return nickname


def _add_provider_basic(p_type, set_active=False, allow_back=False):
    """Add provider via prompts. If allow_back, return None when user enters 0."""
    models = AI_PROVIDERS[p_type]["models"]
    default_ep = AI_PROVIDERS[p_type]["endpoint"]
    step = 0
    api_key = model = endpoint = nickname = None

    while True:
        if step == 0:
            print_provider_key_help(p_type)
            if allow_back:
                api_key = _setup_basic_read("🔑 API key")
                if api_key is None:
                    return None
                if api_key == "BACK":
                    return "BACK"
            else:
                try:
                    api_key = input("🔑 API key: ").strip()
                except (EOFError, KeyboardInterrupt):
                    return None
            if not api_key:
                if allow_back:
                    print("   ❌ API key cannot be empty.")
                    continue
                return None
            step = 1

        elif step == 1:
            model_hint = ", ".join(models)
            if allow_back:
                print(f"  Models: 0 = back, then: {', '.join(f'{i+1}. {m}' for i, m in enumerate(models))}")
                raw = _setup_basic_read(f"📦 Model")
                if raw is None:
                    return None
                if raw == "BACK":
                    step = 0
                    continue
                try:
                    midx = int(raw) - 1
                    if 0 <= midx < len(models):
                        model = models[midx]
                    else:
                        model = raw
                except ValueError:
                    model = raw
            else:
                try:
                    model = input(f"📦 Model ({model_hint}): ").strip()
                except (EOFError, KeyboardInterrupt):
                    return None
            if not model:
                if allow_back:
                    print("   ❌ Model cannot be empty.")
                    continue
                return None
            step = 2

        elif step == 2:
            if allow_back:
                endpoint = _setup_basic_read(f"🌐 Endpoint [{default_ep}]")
                if endpoint is None:
                    return None
                if endpoint == "BACK":
                    step = 1
                    continue
                endpoint = endpoint or default_ep
            else:
                try:
                    endpoint = input("🌐 Endpoint: ").strip() or default_ep
                except (EOFError, KeyboardInterrupt):
                    return None
            step = 3

        elif step == 3:
            existing = load_providers()
            default_nick = _generate_nickname(p_type, model, existing)
            if allow_back:
                nickname = _setup_basic_read(f"🏷  Nickname [{default_nick}]")
                if nickname is None:
                    return None
                if nickname == "BACK":
                    step = 2
                    continue
                nickname = nickname or default_nick
            else:
                try:
                    nickname = input("🏷  Nickname: ").strip() or default_nick
                except (EOFError, KeyboardInterrupt):
                    return None

            add_provider(nickname, p_type, model, endpoint, api_key)
            if set_active:
                cfg = load_config() or {}
                cfg["active_provider"] = nickname
                save_config(cfg)
            return nickname


def test_provider_connection(nickname=None):
    import urllib.request
    import urllib.error
    if nickname is None:
        cfg = load_config() or {}
        nickname = cfg.get("active_provider", "")
    if not nickname: return False, "No active provider."

    providers = load_providers()
    secrets = load_secrets()
    if nickname not in providers: return False, f"Not found: {nickname}"

    info = providers[nickname]
    api_key = secrets.get(nickname, "")
    if not api_key: return False, "No API key."

    headers = {"Content-Type": "application/json"}
    if info["provider"] == "claude":
        body = {"model": info["model"], "max_tokens": 10, "messages": [{"role": "user", "content": "hi"}]}
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
    else:
        body = {"model": info["model"], "messages": [{"role": "user", "content": "hi"}], "max_tokens": 10}
        headers["Authorization"] = f"Bearer {api_key}"

    headers["User-Agent"] = NOVA_HTTP_USER_AGENT

    try:
        req = urllib.request.Request(info["endpoint"], data=json.dumps(body).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp: resp.read()
        return True, f"✅ Connection to '{nickname}' successful!"
    except Exception as e: return False, f"❌ Failed: {e}"


def _ensure_kb_file(kb_path):
    kb_file = os.path.join(kb_path, "kb.json")
    if not os.path.exists(kb_file):
        with open(kb_file, "w") as fh: json.dump([], fh, indent=2)
    else:
        try:
            with open(kb_file, "r") as fh: data = json.load(fh)
            print(f"   ✅ Found kb.json ({len(data)} entries)")
        except: pass


def _print_summary(config):
    config = config or {}
    active_kb = config.get("active_kb", "")
    kbs = load_kbs()
    active_path = kbs.get(active_kb, "N/A")
    active_ai = config.get("active_provider", "")
    providers = load_providers()

    print("\n╔══════════════════════════════════════════╗")
    print("║          ✅  Setup Complete!               ║")
    print("╚══════════════════════════════════════════╝")
    print(f"   KB       : {active_kb} ({active_path})")
    print(f"   User     : {config.get('added_by', 'N/A')}")
    print(f"   AI       : {active_ai if active_ai else 'not configured'}")
    print(f"   KBs      : {len(kbs)} configured")
    print(f"   AI Provis: {len(providers)} configured\n")


def get_config():
    cfg = load_config()
    if cfg is None: cfg = interactive_setup()
    return cfg


def secrets_path():
    return SECRETS_FILE


def config_path():
    """Return path to main config file (for display)."""
    return CONFIG_FILE


def set_active_provider_model(model):
    """Update the active provider's model. Returns True if success."""
    model = (model or "").strip()
    if not model:
        return False
    cfg = load_config()
    active = (cfg or {}).get("active_provider", "")
    if not active:
        return False
    providers = load_providers()
    if active not in providers:
        return False
    providers[active]["model"] = model
    save_providers(providers)
    return True


def set_active_provider_apikey(api_key):
    """Update the active provider's API key. Returns True if success."""
    api_key = (api_key or "").strip() if api_key is not None else ""
    cfg = load_config()
    active = (cfg or {}).get("active_provider", "")
    if not active:
        return False
    secrets = load_secrets()
    secrets[active] = api_key
    save_secrets(secrets)
    return True


def reset_all_config():
    """Wipe all Nova config (config, providers, secrets, kb_sources). Returns True."""
    try:
        for path in (CONFIG_FILE, PROVIDERS_FILE, SECRETS_FILE, KBS_FILE):
            if os.path.exists(path):
                os.remove(path)
        return True
    except OSError:
        return False

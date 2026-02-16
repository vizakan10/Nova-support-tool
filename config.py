#!/usr/bin/env python3
"""
Nova CLI — Configuration Manager
Multi-provider AI support, secrets management, multi-KB sources, interactive setup.
"""

import os
import json
import getpass

# ─── Paths ───────────────────────────────────────────────────────────────────
CONFIG_DIR = os.path.expanduser("~/.nova")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
PROVIDERS_FILE = os.path.join(CONFIG_DIR, "providers.json")
SECRETS_FILE = os.path.join(CONFIG_DIR, "secrets.json")
KBS_FILE = os.path.join(CONFIG_DIR, "kb_sources.json")

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
    },
    "openai": {
        "endpoint": "https://api.openai.com/v1/chat/completions",
        "models": ["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo", "Other"],
    },
    "claude": {
        "endpoint": "https://api.anthropic.com/v1/messages",
        "models": [
            "claude-3-5-sonnet-20241022",
            "claude-3-opus-20240229",
            "Other",
        ],
    },
    "deepseek": {
        "endpoint": "https://api.deepseek.com/v1/chat/completions",
        "models": ["deepseek-chat", "deepseek-coder", "Other"],
    },
    "ollama": {
        "endpoint": "http://localhost:11434/v1/chat/completions",
        "models": ["llama3", "mistral", "codellama", "Other"],
    },
    "google": {
        "endpoint": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "models": ["gemini-2.0-flash", "gemini-1.5-pro", "Other"],
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
#  FILE I/O
# ═══════════════════════════════════════════════════════════════════════════════

def _ensure_dir():
    os.makedirs(CONFIG_DIR, exist_ok=True)


def _load_json(path, default=None):
    if default is None:
        default = {}
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
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
    if not cfg:
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
    """Register a new Knowledge Base folder."""
    kbs = load_kbs()
    kbs[nickname] = os.path.abspath(os.path.expanduser(path))
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
    providers = load_providers()
    secrets = load_secrets()

    providers[nickname] = {
        "provider": provider_type,
        "model": model,
        "endpoint": endpoint,
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


def _setup_rich(q):
    style = _get_style(q)
    print("\n╔══════════════════════════════════════════╗")
    print("║        🚀  Nova CLI — First Setup        ║")
    print("╚══════════════════════════════════════════╝\n")

    kb_path = q.text(
        "📁 KB folder path (or path to kb.json):",
        instruction="e.g. /mnt/c/Users/you/OneDrive/Nova-KB  or  .../Nova-tool-Db/kb.json",
        style=style,
    ).ask()
    if kb_path is None: return None
    kb_path = os.path.expanduser(kb_path.strip().strip('"\''))

    if not kb_path:
        print("   ❌ KB path cannot be empty.")
        return None

    # If user entered path to kb.json, use the folder that contains it
    if kb_path.endswith("kb.json"):
        kb_path = os.path.dirname(os.path.normpath(kb_path))

    # On WSL/Linux, accept Windows path and convert: C:\Users\... -> /mnt/c/Users/...
    _path = kb_path.replace("\\", "/")
    if _path.startswith("C:/") or _path.startswith("c:/"):
        kb_path = "/mnt/c" + _path[2:]
    elif len(_path) >= 2 and _path[1] == ":" and _path[0].upper() in "CDEF":
        drive = _path[0].lower()
        kb_path = f"/mnt/{drive}" + _path[2:].replace("\\", "/")

    if not os.path.isdir(kb_path):
        create = q.confirm(f"   '{kb_path}' doesn't exist. Create it?", default=True, style=style).ask()
        if create:
            os.makedirs(kb_path, exist_ok=True)
        else:
            return None

    _ensure_kb_file(kb_path)
    add_kb_source("main", kb_path)

    cfg = load_config() or {}
    cfg["active_kb"] = "main"
    cfg["added_by"] = getpass.getuser()
    save_config(cfg)

    # First AI provider
    provider_choices = list(AI_PROVIDERS.keys()) + ["Skip (no AI)"]
    p_type = q.select("🤖 Choose AI provider (optional):", choices=provider_choices, style=style).ask()
    if p_type and p_type != "Skip (no AI)":
        _add_provider_rich(q, style, p_type, set_active=True)

    _print_summary(cfg)
    return cfg


def _setup_basic():
    print("\n══════════════════════════════════════════\n        🚀  Nova CLI — First Setup\n══════════════════════════════════════════\n")
    try:
        kb_path = input("📁 KB folder path (or path to kb.json): ").strip().strip('"\'')
    except (EOFError, KeyboardInterrupt): return None
    kb_path = os.path.expanduser(kb_path)

    if not kb_path:
        print("   ❌ KB path cannot be empty.")
        return None

    if kb_path.endswith("kb.json"):
        kb_path = os.path.dirname(os.path.normpath(kb_path))

    if not os.path.isdir(kb_path):
        yn = input(f"   '{kb_path}' doesn't exist. Create? [Y/n]: ").strip().lower()
        if yn in ("", "y", "yes"): os.makedirs(kb_path, exist_ok=True)
        else: return None

    _ensure_kb_file(kb_path)
    add_kb_source("main", kb_path)

    print("\n  Available AI providers:")
    plist = list(AI_PROVIDERS.keys())
    for i, p in enumerate(plist, 1): print(f"    {i}. {p}")
    print(f"    {len(plist)+1}. Skip (no AI)")

    try:
        choice = input(f"  Choose [1-{len(plist)+1}]: ").strip()
        idx = int(choice) - 1
        if 0 <= idx < len(plist):
            _add_provider_basic(plist[idx], set_active=True)
    except (ValueError, IndexError, EOFError, KeyboardInterrupt): pass

    cfg = load_config() or {}
    cfg["active_kb"] = "main"
    cfg["added_by"] = getpass.getuser()
    save_config(cfg)
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
            for i, p in enumerate(plist, 1): print(f"    {i}. {p}")
            try:
                c = int(input(f"  Choose [1-{len(plist)}]: ").strip()) - 1
                p_type = plist[c]
            except: return None
        return _add_provider_basic(p_type, set_active=True)


def _add_provider_rich(q, style, p_type, set_active=False):
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
        cfg = load_config()
        cfg["active_provider"] = nickname
        save_config(cfg)
    return nickname


def _add_provider_basic(p_type, set_active=False):
    api_key = input("🔑 API key: ").strip()
    if not api_key: return None
    model = input(f"📦 Model ({', '.join(AI_PROVIDERS[p_type]['models'])}): ").strip()
    endpoint = input("🌐 Endpoint: ").strip() or AI_PROVIDERS[p_type]["endpoint"]
    existing = load_providers()
    nickname = input(f"🏷  Nickname: ").strip() or _generate_nickname(p_type, model, existing)

    add_provider(nickname, p_type, model, endpoint, api_key)
    if set_active:
        cfg = load_config()
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
    cfg = load_config()
    active = (cfg or {}).get("active_provider", "")
    if not active:
        return False
    providers = load_providers()
    if active not in providers:
        return False
    providers[active]["model"] = model.strip()
    save_providers(providers)
    return True


def set_active_provider_apikey(api_key):
    """Update the active provider's API key. Returns True if success."""
    cfg = load_config()
    active = (cfg or {}).get("active_provider", "")
    if not active:
        return False
    secrets = load_secrets()
    secrets[active] = api_key.strip()
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

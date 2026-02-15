#!/usr/bin/env python3
"""
Nova CLI — Configuration Manager
Multi-provider AI support, secrets management, interactive setup.

Storage layout (~/.nova/):
    config.json      — kb_path, added_by, active_provider
    providers.json   — {nickname: {provider, model, endpoint}}
    secrets.json     — {nickname: api_key}         (separate for safety)
"""

import os
import json
import getpass

# ─── Paths ───────────────────────────────────────────────────────────────────
CONFIG_DIR = os.path.expanduser("~/.nova")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
PROVIDERS_FILE = os.path.join(CONFIG_DIR, "providers.json")
SECRETS_FILE = os.path.join(CONFIG_DIR, "secrets.json")

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
#  FILE I/O  (config.json, providers.json, secrets.json)
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
    """Load core config (kb_path, added_by, active_provider)."""
    cfg = _load_json(CONFIG_FILE)
    if not cfg or "kb_path" not in cfg:
        return None
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


# ═══════════════════════════════════════════════════════════════════════════════
#  PROVIDER MANAGEMENT
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
        cfg = {"kb_path": "", "added_by": getpass.getuser(), "active_provider": ""}
    cfg["active_provider"] = nickname
    save_config(cfg)
    return True


def get_active_ai_config():
    """
    Return the active provider's full config dict for use by nova up.

    Returns: {"provider": ..., "model": ..., "endpoint": ..., "api_key": ...}
    or None if no active provider.
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
#  INTERACTIVE SETUP  (first-time)
# ═══════════════════════════════════════════════════════════════════════════════

def interactive_setup():
    """
    First-time setup wizard.
    Sets KB path + optionally adds the first AI provider.
    """
    try:
        import questionary
        return _setup_rich(questionary)
    except ImportError:
        print(
            "\n  ⚠  'questionary' not installed — using basic prompts."
            "\n     For the full experience:  pip install questionary>=2.0.0\n"
        )
        return _setup_basic()


def _get_style(q):
    return q.Style(
        [
            ("qmark", "fg:#36a3ff bold"),
            ("question", "bold"),
            ("answer", "fg:#36a3ff bold"),
            ("pointer", "fg:#0055ff bold"),
            ("highlighted", "fg:#0055ff bold"),
            ("instruction", "fg:#888888 italic"),
        ]
    )


# ── Rich setup ───────────────────────────────────────────────────────────────
def _setup_rich(q):
    style = _get_style(q)

    print()
    print("╔══════════════════════════════════════════╗")
    print("║        🚀  Nova CLI — First Setup        ║")
    print("╚══════════════════════════════════════════╝")
    print()

    # ── KB path ──────────────────────────────────────────────────────────
    kb_path = q.text(
        "📁 KB folder path (OneDrive-synced folder):",
        instruction="e.g. /mnt/c/Users/you/OneDrive - IFS/Nova-KB",
        style=style,
    ).ask()
    if kb_path is None:
        return None

    kb_path = os.path.expanduser(kb_path.strip())

    if not kb_path:
        print("   ❌ KB path cannot be empty.")
        return None

    if not os.path.isdir(kb_path):
        create = q.confirm(
            f"   '{kb_path}' doesn't exist. Create it?",
            default=True,
            style=style,
        ).ask()
        if create:
            os.makedirs(kb_path, exist_ok=True)
            print("   ✅ Directory created.")
        else:
            print("   ❌ Setup cancelled.")
            return None

    _ensure_kb_file(kb_path)

    # ── First AI provider (optional) ─────────────────────────────────────
    provider_choices = list(AI_PROVIDERS.keys()) + ["Skip (no AI)"]
    provider_type = q.select(
        "🤖 Choose AI provider (optional):",
        choices=provider_choices,
        style=style,
    ).ask()

    if provider_type and provider_type != "Skip (no AI)":
        _add_provider_rich(q, style, provider_type, set_active=True)

    # ── Save core config ─────────────────────────────────────────────────
    cfg = load_config() or {}
    cfg["kb_path"] = kb_path
    cfg["added_by"] = getpass.getuser()
    if "active_provider" not in cfg:
        cfg["active_provider"] = ""
    save_config(cfg)

    _print_summary(cfg)
    return cfg


# ── Basic setup ──────────────────────────────────────────────────────────────
def _setup_basic():
    print()
    print("══════════════════════════════════════════")
    print("        🚀  Nova CLI — First Setup")
    print("══════════════════════════════════════════")
    print()

    try:
        kb_path = input("📁 KB folder path (OneDrive-synced): ").strip()
    except (EOFError, KeyboardInterrupt):
        return None

    kb_path = os.path.expanduser(kb_path)

    if not kb_path:
        print("   ❌ KB path cannot be empty.")
        return None

    if not os.path.isdir(kb_path):
        yn = input(f"   '{kb_path}' doesn't exist. Create? [Y/n]: ").strip().lower()
        if yn in ("", "y", "yes"):
            os.makedirs(kb_path, exist_ok=True)
        else:
            print("   ❌ Setup cancelled.")
            return None

    _ensure_kb_file(kb_path)

    print("\n  Available AI providers:")
    providers_list = list(AI_PROVIDERS.keys())
    for i, p in enumerate(providers_list, 1):
        print(f"    {i}. {p}")
    print(f"    {len(providers_list)+1}. Skip (no AI)")

    try:
        choice = input(f"  Choose [1-{len(providers_list)+1}]: ").strip()
    except (EOFError, KeyboardInterrupt):
        choice = str(len(providers_list) + 1)

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(providers_list):
            provider_type = providers_list[idx]
            _add_provider_basic(provider_type, set_active=True)
    except (ValueError, IndexError):
        pass

    cfg = load_config() or {}
    cfg["kb_path"] = kb_path
    cfg["added_by"] = getpass.getuser()
    if "active_provider" not in cfg:
        cfg["active_provider"] = ""
    save_config(cfg)

    _print_summary(cfg)
    return cfg


# ═══════════════════════════════════════════════════════════════════════════════
#  ADD PROVIDER  (interactive — used by setup and `nova add-llm`)
# ═══════════════════════════════════════════════════════════════════════════════

def add_provider_interactive(provider_type=None):
    """
    Interactively add a new AI provider.
    Called by `nova add-llm` and during `nova setup`.
    """
    try:
        import questionary
        q = questionary
        style = _get_style(q)
        if provider_type is None:
            provider_type = q.select(
                "🤖 Choose AI provider:",
                choices=list(AI_PROVIDERS.keys()),
                style=style,
            ).ask()
            if not provider_type:
                return None
        return _add_provider_rich(q, style, provider_type, set_active=True)
    except ImportError:
        if provider_type is None:
            print("  Available providers:")
            plist = list(AI_PROVIDERS.keys())
            for i, p in enumerate(plist, 1):
                print(f"    {i}. {p}")
            try:
                c = int(input(f"  Choose [1-{len(plist)}]: ").strip()) - 1
                provider_type = plist[c]
            except (ValueError, IndexError, EOFError, KeyboardInterrupt):
                return None
        return _add_provider_basic(provider_type, set_active=True)


def _add_provider_rich(q, style, provider_type, set_active=False):
    """Add a provider using questionary prompts. Returns nickname or None."""
    # API key
    api_key = q.password("🔑 API key:", style=style).ask()
    if api_key is None:
        return None
    api_key = api_key.strip()
    if not api_key:
        print("   ❌ API key cannot be empty.")
        return None

    # Model
    models = AI_PROVIDERS[provider_type]["models"]
    model = q.select("📦 Model:", choices=models, style=style).ask()
    if model == "Other":
        model = q.text("   Enter model name:", style=style).ask()
        if not model or not model.strip():
            print("   ❌ Model name cannot be empty.")
            return None
        model = model.strip()

    # Endpoint
    default_ep = AI_PROVIDERS[provider_type]["endpoint"]
    endpoint = (
        q.text(
            "🌐 API endpoint (blank = default):",
            default=default_ep,
            style=style,
        ).ask()
        or default_ep
    )

    # Nickname
    existing = load_providers()
    default_nick = _generate_nickname(provider_type, model, existing)
    nickname = q.text(
        "🏷  Nickname for this provider:",
        default=default_nick,
        style=style,
    ).ask()
    if not nickname or not nickname.strip():
        nickname = default_nick
    nickname = nickname.strip()

    # Deduplicate
    seq = 1
    base = nickname
    while nickname in existing:
        nickname = f"{base}-{seq}"
        seq += 1

    # Save
    add_provider(nickname, provider_type, model, endpoint, api_key)

    if set_active:
        cfg = load_config() or {"kb_path": "", "added_by": getpass.getuser()}
        cfg["active_provider"] = nickname
        save_config(cfg)

    print(f"   ✅ Provider '{nickname}' added and set as active.")
    return nickname


def _add_provider_basic(provider_type, set_active=False):
    """Add a provider using basic input prompts."""
    try:
        api_key = input("🔑 API key: ").strip()
        if not api_key:
            print("   ❌ API key cannot be empty.")
            return None

        print(f"   Models: {', '.join(AI_PROVIDERS[provider_type]['models'])}")
        model = input("📦 Model: ").strip()
        if not model:
            print("   ❌ Model name cannot be empty.")
            return None

        endpoint = (
            input("🌐 Endpoint (blank=default): ").strip()
            or AI_PROVIDERS[provider_type]["endpoint"]
        )

        existing = load_providers()
        default_nick = _generate_nickname(provider_type, model, existing)
        nickname = input(f"🏷  Nickname [{default_nick}]: ").strip() or default_nick

        # Deduplicate
        seq = 1
        base = nickname
        while nickname in existing:
            nickname = f"{base}-{seq}"
            seq += 1

    except (EOFError, KeyboardInterrupt):
        print("\n   Cancelled.")
        return None

    add_provider(nickname, provider_type, model, endpoint, api_key)

    if set_active:
        cfg = load_config() or {"kb_path": "", "added_by": getpass.getuser()}
        cfg["active_provider"] = nickname
        save_config(cfg)

    print(f"   ✅ Provider '{nickname}' added and set as active.")
    return nickname


# ═══════════════════════════════════════════════════════════════════════════════
#  TEST PROVIDER CONNECTION
# ═══════════════════════════════════════════════════════════════════════════════

def test_provider_connection(nickname=None):
    """
    Send a tiny test request to the provider.
    If *nickname* is None, tests the active provider.
    Returns (success: bool, message: str).
    """
    import urllib.request
    import urllib.error

    if nickname is None:
        cfg = load_config() or {}
        nickname = cfg.get("active_provider", "")
        if not nickname:
            return False, "No active provider configured."

    providers = load_providers()
    secrets = load_secrets()

    if nickname not in providers:
        return False, f"Provider '{nickname}' not found."

    info = providers[nickname]
    api_key = secrets.get(nickname, "")
    provider_type = info.get("provider", "")
    model = info.get("model", "")
    endpoint = info.get("endpoint", "")

    if not api_key:
        return False, f"No API key for '{nickname}'."

    # Build a minimal test request
    if provider_type == "claude":
        body = {
            "model": model,
            "max_tokens": 10,
            "messages": [{"role": "user", "content": "hi"}],
        }
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
    else:
        body = {
            "model": model,
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 10,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(endpoint, data=payload, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        return True, f"✅ Connection to '{nickname}' ({provider_type}/{model}) successful!"
    except urllib.error.HTTPError as exc:
        msg = exc.read().decode("utf-8", errors="replace")[:150]
        return False, f"❌ HTTP {exc.code}: {msg}"
    except Exception as exc:
        return False, f"❌ Connection failed: {exc}"


# ═══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _ensure_kb_file(kb_path):
    kb_file = os.path.join(kb_path, "kb.json")
    if not os.path.exists(kb_file):
        with open(kb_file, "w", encoding="utf-8") as fh:
            json.dump([], fh, indent=2)
        print("   ✅ Created empty kb.json")
    else:
        try:
            with open(kb_file, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            print(f"   ✅ Found kb.json ({len(data)} entries)")
        except Exception:
            print("   ✅ Found kb.json")


def _print_summary(config):
    active = config.get("active_provider", "")
    providers = load_providers()
    ai_info = providers.get(active, {})

    print()
    print("╔══════════════════════════════════════════╗")
    print("║          ✅  Setup Complete!               ║")
    print("╚══════════════════════════════════════════╝")
    print(f"   KB path  : {config.get('kb_path', 'N/A')}")
    print(f"   User     : {config.get('added_by', 'N/A')}")
    if active and ai_info:
        print(f"   AI       : {active} ({ai_info.get('provider')}/{ai_info.get('model')})")
    else:
        print("   AI       : not configured")
    print(f"   Config   : {CONFIG_DIR}/")
    print(f"   Providers: {len(providers)} configured")
    print()


def get_config():
    """Return existing config or launch setup if missing."""
    cfg = load_config()
    if cfg is None:
        print("\n  ⚠  Nova is not configured yet.\n")
        cfg = interactive_setup()
    return cfg


def secrets_path():
    """Return the absolute path to the secrets file."""
    return SECRETS_FILE

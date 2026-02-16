#!/usr/bin/env python3
"""
Nova CLI — Framework Reliability Agent
Main entry point for all nova commands.
"""

import os
import re
import sys
import json
import subprocess
import urllib.request
import urllib.error
from datetime import datetime

VERSION = "2.0.0"

# Fetched on first run each day; you can publish announcements by updating this file in the repo
ANNOUNCEMENTS_URL = "https://raw.githubusercontent.com/vizakan10/Nova-support-tool/main/announcements.json"
ANNOUNCE_STATE_FILE = os.path.join(os.path.expanduser("~/.nova"), "announce_state.json")


from config import (
    get_config,
    interactive_setup,
    load_config,
    load_providers,
    load_kbs,
    save_kbs,
    add_provider_interactive,
    add_provider,
    remove_provider,
    switch_provider,
    list_all_providers,
    get_active_ai_config,
    test_provider_connection,
    secrets_path,
    config_path,
    add_kb_source,
    remove_kb_source,
    switch_kb,
    list_all_kbs,
    get_active_kb_path,
    normalize_kb_path,
    set_active_provider_model,
    set_active_provider_apikey,
    reset_all_config,
    save_current_as_profile,
    CONFIG_FILE,
    AI_PROVIDERS,
)
from kb_manager import (
    fuzzy_search,
    load_kb,
    add_entry,
    delete_entry,
    resolve_conflicts,
    sanitize,
)


# ═══════════════════════════════════════════════════════════════════════════════
#  ANSI HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

class C:
    """ANSI colour codes — gracefully degrades if redirected."""

    _enabled = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

    RESET = "\033[0m" if _enabled else ""
    BOLD = "\033[1m" if _enabled else ""
    DIM = "\033[2m" if _enabled else ""
    ITALIC = "\033[3m" if _enabled else ""
    RED = "\033[91m" if _enabled else ""
    GREEN = "\033[92m" if _enabled else ""
    YELLOW = "\033[93m" if _enabled else ""
    BLUE = "\033[94m" if _enabled else ""
    MAGENTA = "\033[95m" if _enabled else ""
    CYAN = "\033[96m" if _enabled else ""
    WHITE = "\033[97m" if _enabled else ""
    ORANGE = "\033[38;5;208m" if _enabled else ""


# ═══════════════════════════════════════════════════════════════════════════════
#  BANNER
# ═══════════════════════════════════════════════════════════════════════════════

BANNER = f"""{C.ORANGE}{C.BOLD}
    ╔═══════════════════════════════════════════════╗
    ║   ███╗   ██╗  ██████╗  ██╗   ██╗  █████╗     ║
    ║   ████╗  ██║ ██╔═══██╗ ██║   ██║ ██╔══██╗    ║
    ║   ██╔██╗ ██║ ██║   ██║ ██║   ██║ ███████║    ║
    ║   ██║╚██╗██║ ██║   ██║ ╚██╗ ██╔╝ ██╔══██║    ║
    ║   ██║ ╚████║ ╚██████╔╝  ╚████╔╝  ██║  ██║    ║
    ║   ╚═╝  ╚═══╝  ╚═════╝    ╚═══╝   ╚═╝  ╚═╝    ║
    ║         [ SUPPORT TOOL ]  v{VERSION} PRO         ║
    ╚═══════════════════════════════════════════════╝{C.RESET}
{C.ORANGE}    Terminal Error Resolution Tool{C.RESET}
"""


# ═══════════════════════════════════════════════════════════════════════════════
#  ERROR DETECTION PATTERNS
# ═══════════════════════════════════════════════════════════════════════════════

_ERROR_PATTERNS = [
    re.compile(r"(?i)Traceback \(most recent call last\)"),
    re.compile(r"(?i)(ModuleNotFoundError|ImportError|FileNotFoundError|PermissionError)"),
    re.compile(r"(?i)(SyntaxError|TypeError|ValueError|KeyError|AttributeError|NameError)"),
    re.compile(r"(?i)(RuntimeError|OSError|IOError|ConnectionError|TimeoutError)"),
    re.compile(r"(?i)(npm ERR!|Error:|ERR_|ENOENT|EACCES|ENOSPC|ECONNREFUSED)"),
    re.compile(r"(?i)(FATAL|PANIC|ABORT|SEGFAULT|core dumped)"),
    re.compile(r"(?i)(command not found|no such file|permission denied)"),
    re.compile(r"(?i)(BUILD FAILED|COMPILATION ERROR|LINK ERROR)"),
    re.compile(r"(?i)(failed|error|exception|denied|crash)"),
    re.compile(r"\b(401|403|404|500|502|503)\b"),
]


# ═══════════════════════════════════════════════════════════════════════════════
#  TERMINAL OUTPUT CAPTURE
# ═══════════════════════════════════════════════════════════════════════════════

def get_terminal_output():
    """
    Capture the last terminal output.

    1. Piped stdin  (echo err | nova up)
    2. Bash history re-run
    3. Manual paste fallback
    """
    if not sys.stdin.isatty():
        data = sys.stdin.read().strip()
        if data:
            return data

    output = _try_bash_history()
    if output:
        return output

    return _prompt_paste()


def _try_bash_history():
    histfile = os.environ.get("HISTFILE", os.path.expanduser("~/.bash_history"))

    if not os.path.isfile(histfile):
        return None

    try:
        with open(histfile, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return None

    last_cmd = None
    for line in reversed(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith("nova ") and stripped != "nova":
            last_cmd = stripped
            break

    if not last_cmd:
        return None

    print(f"  {C.DIM}Last command:{C.RESET} {C.CYAN}{last_cmd}{C.RESET}")

    try:
        ans = input(f"  {C.YELLOW}Re-run to capture output? [Y/n]: {C.RESET}").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return None

    if ans not in ("", "y", "yes"):
        return None

    try:
        result = subprocess.run(
            last_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            executable="/bin/bash",
        )
        combined = (result.stdout or "") + "\n" + (result.stderr or "")
        return combined.strip() or None
    except subprocess.TimeoutExpired:
        print(f"  {C.YELLOW}⚠  Command timed out after 30 s.{C.RESET}")
    except Exception:
        pass
    return None


def _prompt_paste():
    print(f"  {C.YELLOW}📋 Paste the error below (Ctrl+D when done):{C.RESET}")
    print(f"  {C.DIM}{'─' * 44}{C.RESET}")

    buf = []
    try:
        while True:
            buf.append(input())
    except EOFError:
        pass
    except KeyboardInterrupt:
        return None

    return "\n".join(buf).strip() or None


# ═══════════════════════════════════════════════════════════════════════════════
#  ERROR EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

def detect_error(text):
    if not text:
        return None

    scored_lines = []

    for line in text.strip().splitlines():
        clean = line.strip()
        if not clean or len(clean) < 6:
            continue
        hits = sum(1 for p in _ERROR_PATTERNS if p.search(clean))
        if hits:
            scored_lines.append((clean, hits))

    if not scored_lines:
        return None

    scored_lines.sort(key=lambda x: x[1], reverse=True)

    top_score = scored_lines[0][1]
    top_tier = [l for l, s in scored_lines if s == top_score]

    specific = [l for l in top_tier if ":" in l]
    if specific:
        return specific[-1]

    return top_tier[-1]


# ═══════════════════════════════════════════════════════════════════════════════
#  AI FALLBACK
# ═══════════════════════════════════════════════════════════════════════════════

_AI_PROMPT = """\
You are a senior DevOps engineer helping a colleague.
They encountered this error:

{error}

Respond in EXACTLY this format (no extra text):
Solution: <one-sentence explanation>
Command: <exact CLI command to fix it>
"""


def call_ai(error_text, ai_config):
    """
    Call the AI using the provided ai_config dict.
    ai_config must have: provider, model, endpoint, api_key.
    """
    provider = ai_config.get("provider", "")
    api_key = ai_config.get("api_key", "")
    model = ai_config.get("model", "")
    endpoint = ai_config.get("endpoint", "")

    if not all([provider, api_key, model, endpoint]):
        return None

    prompt = _AI_PROMPT.format(error=sanitize(error_text))

    if provider == "claude":
        body = {
            "model": model,
            "max_tokens": 300,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
    else:
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a concise DevOps assistant."},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 300,
            "temperature": 0.2,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(endpoint, data=payload, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        msg = exc.read().decode("utf-8", errors="replace")[:200]
        print(f"  {C.RED}⚠  AI API error ({exc.code}): {msg}{C.RESET}")
        return None
    except Exception as exc:
        print(f"  {C.RED}⚠  AI request failed: {exc}{C.RESET}")
        return None

    if provider == "claude":
        ai_text = (data.get("content") or [{}])[0].get("text", "")
    else:
        ai_text = (
            (data.get("choices") or [{}])[0]
            .get("message", {})
            .get("content", "")
        )

    solution, command = "", ""
    for line in ai_text.splitlines():
        low = line.strip().lower()
        if low.startswith("solution:"):
            solution = line.split(":", 1)[1].strip()
        elif low.startswith("command:"):
            command = line.split(":", 1)[1].strip().strip("`").strip()

    return {
        "solution": solution or ai_text.strip(),
        "command": command,
    }


_AI_ASK_PROMPT = """\
You are a concise technical assistant. Answer the following in a clear, short way.

Question: {query}
"""


def call_ai_ask(query, ai_config):
    """Call AI with a free-form question. Returns response text or None."""
    if not query or not ai_config:
        return None
    provider = ai_config.get("provider", "")
    api_key = ai_config.get("api_key", "")
    model = ai_config.get("model", "")
    endpoint = ai_config.get("endpoint", "")
    if not all([provider, api_key, model, endpoint]):
        return None
    prompt = _AI_ASK_PROMPT.format(query=query.strip())
    if provider == "claude":
        body = {"model": model, "max_tokens": 500, "messages": [{"role": "user", "content": prompt}]}
        headers = {"Content-Type": "application/json", "x-api-key": api_key, "anthropic-version": "2023-06-01"}
    else:
        body = {
            "model": model,
            "messages": [{"role": "system", "content": "You are a concise technical assistant."}, {"role": "user", "content": prompt}],
            "max_tokens": 500,
            "temperature": 0.3,
        }
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(endpoint, data=payload, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"  {C.RED}⚠  AI request failed: {exc}{C.RESET}")
        return None
    if provider == "claude":
        return (data.get("content") or [{}])[0].get("text", "")
    return (data.get("choices") or [{}])[0].get("message", {}).get("content", "")


# ═══════════════════════════════════════════════════════════════════════════════
#  DISPLAY HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _box(lines, colour=C.BLUE):
    width = max((len(l) for l in lines), default=40) + 4
    width = min(max(width, 44), 72)
    bar = "─" * width

    print(f"  {colour}{bar}{C.RESET}")
    for line in lines:
        print(f"  {colour}│{C.RESET} {line}")
    print(f"  {colour}{bar}{C.RESET}")


def display_solution(entry, score=None, source="KB"):
    error = entry.get("error", "N/A")
    solution = entry.get("solution", "N/A")
    command = entry.get("command", "")
    added_by = entry.get("added_by", "")

    if source == "KB":
        header = f"{C.GREEN}{C.BOLD}📚 Solution Found"
        if score is not None:
            header += f"  ({score}% match)"
        header += C.RESET
    else:
        header = f"{C.CYAN}{C.BOLD}🤖 AI Suggestion{C.RESET}"

    body = [
        f"{C.BOLD}Error:{C.RESET}    {error}",
        f"{C.BOLD}Solution:{C.RESET} {solution}",
    ]
    if command:
        body.append(f"{C.BOLD}Command:{C.RESET}  {C.CYAN}{command}{C.RESET}")
    if added_by:
        body.append(f"{C.DIM}Added by: {added_by}{C.RESET}")

    print()
    print(f"  {header}")
    _box(body, colour=C.GREEN if source == "KB" else C.CYAN)

    return command


def _ask_yn(prompt, default_yes=True):
    suffix = "[Y/n]" if default_yes else "[y/N]"
    try:
        ans = input(f"  {C.YELLOW}{prompt} {suffix}: {C.RESET}").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    if default_yes:
        return ans not in ("n", "no")
    return ans in ("y", "yes")


def _active_env():
    """Print Active Environment block (Config, KB path, Secrets path, AI host)."""
    cfg_path = config_path()
    kb_path = get_active_kb_path()
    kb_display = os.path.join(kb_path, "kb.json") if kb_path else "—"
    sec_path = secrets_path()
    cfg = load_config() or {}
    active_prov = cfg.get("active_provider", "")
    providers = load_providers()
    info = providers.get(active_prov, {}) if active_prov else {}
    ai_display = f"{info.get('provider', '—')} ({info.get('model', '—')})" if info else "—"
    print(f"  {C.ORANGE}{'─' * 52}{C.RESET}")
    print(f"  {C.ORANGE}{C.BOLD}  Active Environment{C.RESET}")
    print(f"  {C.ORANGE}{'─' * 52}{C.RESET}")
    print(f"  {C.BOLD}  Config{C.RESET}   {C.DIM}{cfg_path}{C.RESET}")
    print(f"  {C.BOLD}  KB File{C.RESET}   {C.DIM}{kb_display}{C.RESET}")
    print(f"  {C.BOLD}  Secrets{C.RESET}   {C.DIM}{sec_path}{C.RESET}")
    print(f"  {C.BOLD}  AI Host{C.RESET}   {C.DIM}{ai_display}{C.RESET}")
    print(f"  {C.ORANGE}{'─' * 52}{C.RESET}\n")


def _run_command(command):
    if not command:
        return False

    if not _ask_yn("▶ Run this command?"):
        return False

    print(f"  {C.DIM}$ {command}{C.RESET}")

    try:
        rc = subprocess.call(command, shell=True, executable="/bin/bash", timeout=120)
        if rc == 0:
            print(f"  {C.GREEN}✅ Command succeeded.{C.RESET}")
            return True
        else:
            print(f"  {C.RED}❌ Exited with code {rc}.{C.RESET}")
    except subprocess.TimeoutExpired:
        print(f"  {C.YELLOW}⚠  Command timed out.{C.RESET}")
    except Exception as exc:
        print(f"  {C.RED}❌ {exc}{C.RESET}")

    return False


# ═══════════════════════════════════════════════════════════════════════════════
#  COMMANDS
# ═══════════════════════════════════════════════════════════════════════════════

# ── nova up ──────────────────────────────────────────────────────────────────

def cmd_up(config):
    """nova up — Error Intercept Protocol."""
    kb_path = get_active_kb_path()
    if not kb_path or not os.path.isdir(kb_path):
        print(f"  {C.RED}❌ Active KB not found or not configured.{C.RESET}")
        print(f"  {C.DIM}   Run:  nova setup  or  nova use-kb <nickname>{C.RESET}")
        return

    print(f"\n  {C.BLUE}{C.BOLD}🔍 Nova — Error Intercept{C.RESET}")
    
    # Show active KB
    kbs = list_all_kbs()
    active_kb = next((i for i in kbs if i[2]), None)
    if active_kb:
        print(f"  {C.DIM}KB: {active_kb[0]} ({active_kb[1]}){C.RESET}\n")

    # 1. Conflict merge
    merged = resolve_conflicts(kb_path)
    if merged:
        print(f"  {C.GREEN}🔄 Merged {merged} entries from OneDrive conflict files.{C.RESET}\n")

    # 2. Capture output
    raw = get_terminal_output()
    if not raw:
        print(f"  {C.YELLOW}⚠  No input received. Nothing to search.{C.RESET}")
        return

    # 3. Detect error
    error_sig = detect_error(raw)
    if error_sig:
        print(f"  {C.GREEN}✅ Error detected:{C.RESET} {error_sig}")
    else:
        error_sig = raw.strip()[:250]
        print(f"  {C.YELLOW}⚠  No specific error pattern found — searching with full text.{C.RESET}")

    # 4. KB search
    print(f"\n  {C.BLUE}📚 Searching Knowledge Base...{C.RESET}")
    kb_data = load_kb(kb_path)
    print(f"  {C.DIM}   {len(kb_data)} entries loaded.{C.RESET}")

    results = fuzzy_search(error_sig, kb_data, threshold=70)

    if results:
        best_entry, best_score = results[0]
        cmd = display_solution(best_entry, score=best_score, source="KB")
        _run_command(cmd)

        if len(results) > 1:
            print(f"\n  {C.DIM}Other possible matches:{C.RESET}")
            for entry, sc in results[1:4]:
                print(f"  {C.DIM}  • ({sc}%) {entry.get('error', '')[:60]}{C.RESET}")
        return

    print(f"  {C.YELLOW}❌ No match found in KB.{C.RESET}")

    # 5. AI fallback
    ai_config = get_active_ai_config()
    if ai_config:
        p = ai_config.get("provider", "?")
        m = ai_config.get("model", "?")
        print(f"\n  {C.CYAN}🤖 Asking AI ({p}/{m})...{C.RESET}")
        ai_result = call_ai(raw, ai_config)

        if ai_result and ai_result.get("solution"):
            ai_entry = {
                "error": error_sig,
                "solution": ai_result["solution"],
                "command": ai_result.get("command", ""),
            }
            cmd = display_solution(ai_entry, source="AI")
            _run_command(cmd)

            if _ask_yn("💾 Save this fix to the KB for your team?"):
                ok, res = add_entry(
                    kb_path,
                    error_sig,
                    ai_result["solution"],
                    ai_result.get("command", ""),
                    config.get("added_by", "unknown"),
                )
                if ok:
                    print(f"  {C.GREEN}✅ Saved to KB! OneDrive will sync.{C.RESET}")
                else:
                    print(f"  {C.YELLOW}⚠  {res}{C.RESET}")
            return
        else:
            print(f"  {C.YELLOW}⚠  AI couldn't provide a solution.{C.RESET}")

    print(f"\n  {C.DIM}💡 Tip:  Once you fix this, run  nova add  to save the solution.{C.RESET}")
    if not ai_config:
        print(f"  {C.DIM}💡 Run  nova add-llm  to configure an AI provider.{C.RESET}")


# ── nova add ─────────────────────────────────────────────────────────────────

def cmd_add(config):
    """nova add — Add a new error solution to the KB."""
    kb_path = get_active_kb_path()
    if not kb_path or not os.path.isdir(kb_path):
        print(f"  {C.RED}❌ Active KB not configured. Run:  nova setup{C.RESET}")
        return

    print(f"\n  {C.BLUE}{C.BOLD}📝 Nova — Add Solution{C.RESET}")
    
    # Show active KB
    kbs = list_all_kbs()
    active_kb = next((i for i in kbs if i[2]), None)
    if active_kb:
        print(f"  {C.DIM}KB: {active_kb[0]} ({active_kb[1]}){C.RESET}")
    
    print(f"  {C.DIM}{'─' * 44}{C.RESET}\n")

    try:
        error = input(f"  {C.BOLD}Error signature:{C.RESET} ").strip()
        if not error:
            print(f"  {C.RED}❌ Error signature cannot be empty.{C.RESET}")
            return

        solution = input(f"  {C.BOLD}Solution (1 sentence):{C.RESET} ").strip()
        if not solution:
            print(f"  {C.RED}❌ Solution cannot be empty.{C.RESET}")
            return

        command = input(f"  {C.BOLD}Fix command (optional, Enter to skip):{C.RESET} ").strip()
    except (EOFError, KeyboardInterrupt):
        print(f"\n  {C.YELLOW}Cancelled.{C.RESET}")
        return

    print(f"\n  {C.DIM}🔒 Sanitizing input...{C.RESET}")

    ok, result = add_entry(
        kb_path, error, solution, command, config.get("added_by", "unknown")
    )

    if ok:
        print(f"  {C.GREEN}✅ Entry saved to KB!{C.RESET}")
        print(f"  {C.DIM}   OneDrive will sync to the team automatically.{C.RESET}")
        display_solution(result, source="KB")
    else:
        print(f"  {C.YELLOW}⚠  {result}{C.RESET}")


# ── nova setup ───────────────────────────────────────────────────────────────

def cmd_setup():
    """nova setup — (Re)configure Nova."""
    interactive_setup()


# ── nova add-llm ─────────────────────────────────────────────────────────────

def cmd_add_llm():
    """nova add-llm — Add a new AI provider."""
    print(f"\n  {C.BLUE}{C.BOLD}➕ Add AI Provider{C.RESET}\n")
    add_provider_interactive()


# ── nova rm <provider> ───────────────────────────────────────────────────────

def cmd_rm(nickname):
    """nova rm <nickname> — Remove an AI provider."""
    if not nickname:
        print(f"  {C.RED}❌ Usage:  nova rm <provider-nickname>{C.RESET}")
        return

    if remove_provider(nickname):
        print(f"  {C.GREEN}✅ Provider '{nickname}' removed.{C.RESET}")
    else:
        print(f"  {C.RED}❌ Provider '{nickname}' not found.{C.RESET}")
        _show_available_providers()


# ── nova use <provider> ──────────────────────────────────────────────────────

def cmd_use(nickname):
    """nova use <nickname> — Switch active AI provider."""
    if not nickname:
        print(f"  {C.RED}❌ Usage:  nova use <provider-nickname>{C.RESET}")
        return

    if switch_provider(nickname):
        providers = load_providers()
        info = providers.get(nickname, {})
        print(
            f"  {C.GREEN}✅ Active provider set to '{nickname}' "
            f"({info.get('provider')}/{info.get('model')}){C.RESET}"
        )
    else:
        print(f"  {C.RED}❌ Provider '{nickname}' not found.{C.RESET}")
        _show_available_providers()


# ── nova lp ──────────────────────────────────────────────────────────────────

def cmd_lp():
    """nova lp — List all configured AI providers."""
    items = list_all_providers()

    if not items:
        print(f"\n  {C.YELLOW}No AI providers configured.{C.RESET}")
        print(f"  {C.DIM}Run:  nova add-llm{C.RESET}")
        return

    print(f"\n  {C.BLUE}{C.BOLD}🤖 Configured AI Providers{C.RESET}\n")

    for nick, info, is_active in items:
        marker = f"{C.GREEN}● active{C.RESET}" if is_active else f"{C.DIM}○{C.RESET}"
        print(
            f"  {marker}  {C.BOLD}{nick}{C.RESET}"
            f"  {C.DIM}({info.get('provider')}/{info.get('model')}){C.RESET}"
        )

    print()


# ── nova cur ─────────────────────────────────────────────────────────────────

def cmd_cur():
    """nova cur — Show the current active AI provider."""
    cfg = load_config()
    if not cfg:
        print(f"  {C.YELLOW}Nova not configured. Run:  nova setup{C.RESET}")
        return

    active = cfg.get("active_provider", "")
    if not active:
        print(f"  {C.YELLOW}No active AI provider set.{C.RESET}")
        print(f"  {C.DIM}Run:  nova add-llm  or  nova use <nickname>{C.RESET}")
        return

    providers = load_providers()
    info = providers.get(active, {})

    if not info:
        print(f"  {C.YELLOW}Active provider '{active}' not found in providers.{C.RESET}")
        return

    print(f"\n  {C.GREEN}{C.BOLD}● Current Provider{C.RESET}")
    print(f"    Nickname : {C.CYAN}{active}{C.RESET}")
    print(f"    Provider : {info.get('provider', 'N/A')}")
    print(f"    Model    : {info.get('model', 'N/A')}")
    print(f"    Endpoint : {C.DIM}{info.get('endpoint', 'N/A')}{C.RESET}")
    print()


# ── nova test [provider] ────────────────────────────────────────────────────

def cmd_test(nickname=None):
    """nova test [nickname] — Test connection to AI provider."""
    target = nickname or "active provider"
    print(f"\n  {C.BLUE}🔌 Testing connection to {target}...{C.RESET}")

    ok, msg = test_provider_connection(nickname)

    if ok:
        print(f"  {C.GREEN}{msg}{C.RESET}")
    else:
        print(f"  {C.RED}{msg}{C.RESET}")
    print()


# ── nova lk ──────────────────────────────────────────────────────────────────

def cmd_lk():
    """nova lk — List all Knowledge Bases."""
    items = list_all_kbs()
    if not items:
        print(f"\n  {C.YELLOW}No KBs configured.{C.RESET}")
        return

    print(f"\n  {C.BLUE}{C.BOLD}📚 Configured Knowledge Bases{C.RESET}\n")
    for nick, path, is_active in items:
        marker = f"{C.GREEN}● active{C.RESET}" if is_active else f"{C.DIM}○{C.RESET}"
        print(f"  {marker}  {C.BOLD}{nick:<12}{C.RESET} {C.DIM}({path}){C.RESET}")
    print()


# ── nova add-kb <nick> <path> ────────────────────────────────────────────────

def cmd_add_kb(nickname, path):
    """nova add-kb <nickname> <path> — Add a new KB folder."""
    if not nickname or not path:
        print(f"  {C.RED}❌ Usage:  nova add-kb <nickname> <path>{C.RESET}")
        return
    add_kb_source(nickname, path)
    print(f"  {C.GREEN}✅ KB '{nickname}' registered at: {path}{C.RESET}")


# ── nova rm-kb <nick> ───────────────────────────────────────────────────────

def cmd_rm_kb(nickname):
    """nova rm-kb <nickname> — Unlink a KB folder."""
    if not nickname:
        print(f"  {C.RED}❌ Usage:  nova rm-kb <nickname>{C.RESET}")
        return
    if remove_kb_source(nickname):
        print(f"  {C.GREEN}✅ KB '{nickname}' removed.{C.RESET}")
    else:
        print(f"  {C.RED}❌ KB '{nickname}' not found.{C.RESET}")


# ── nova use-kb <nick> ──────────────────────────────────────────────────────

def cmd_use_kb(nickname):
    """nova use-kb <nickname> — Switch active KB."""
    if not nickname:
        print(f"  {C.RED}❌ Usage:  nova use-kb <nickname>{C.RESET}")
        return
    if switch_kb(nickname):
        print(f"  {C.GREEN}✅ Switched to KB: {nickname}{C.RESET}")
    else:
        print(f"  {C.RED}❌ KB '{nickname}' not found.{C.RESET}")


# ── nova cur-kb ─────────────────────────────────────────────────────────────

def cmd_cur_kb():
    """nova cur-kb — Show current active KB and path."""
    items = list_all_kbs()
    active = next((i for i in items if i[2]), None)
    if not active:
        print(f"  {C.YELLOW}No active KB configured.{C.RESET}")
        return
    print(f"\n  {C.GREEN}{C.BOLD}● Current Knowledge Base{C.RESET}")
    print(f"    Nickname : {C.CYAN}{active[0]}{C.RESET}")
    print(f"    Path     : {C.DIM}{active[1]}{C.RESET}\n")


# ── nova secrets-path ────────────────────────────────────────────────────────

def cmd_secrets_path():
    """nova secrets-path — Show where secrets are stored."""
    path = secrets_path()
    exists = os.path.exists(path)
    print(f"\n  {C.BOLD}Secrets file:{C.RESET} {path}")
    print(f"  {C.DIM}Exists: {'yes' if exists else 'no'}{C.RESET}")
    print()


# ── nova fix ─────────────────────────────────────────────────────────────────

def cmd_fix(config):
    """nova fix — Paste error and get instant solution (KB → AI)."""
    kb_path = get_active_kb_path()
    if not kb_path or not os.path.isdir(kb_path):
        print(f"  {C.RED}❌ Active KB not configured. Run:  nova setup{C.RESET}")
        return
    print(f"\n  {C.ORANGE}{C.BOLD}🔧 Nova — Paste & Fix{C.RESET}\n")
    raw = _prompt_paste()
    if not raw:
        print(f"  {C.YELLOW}⚠  No input received.{C.RESET}")
        return
    error_sig = detect_error(raw) or raw.strip()[:250]
    resolve_conflicts(kb_path)
    kb_data = load_kb(kb_path)
    results = fuzzy_search(error_sig, kb_data, threshold=70)
    if results:
        best_entry, best_score = results[0]
        cmd = display_solution(best_entry, score=best_score, source="KB")
        _run_command(cmd)
        return
    ai_config = get_active_ai_config()
    if ai_config:
        print(f"\n  {C.CYAN}🤖 Asking AI...{C.RESET}")
        ai_result = call_ai(raw, ai_config)
        if ai_result and ai_result.get("solution"):
            ai_entry = {"error": error_sig, "solution": ai_result["solution"], "command": ai_result.get("command", "")}
            cmd = display_solution(ai_entry, source="AI")
            _run_command(cmd)
            if _ask_yn("💾 Save this fix to the KB?"):
                ok, res = add_entry(kb_path, error_sig, ai_result["solution"], ai_result.get("command", ""), config.get("added_by", "unknown"))
                if ok:
                    print(f"  {C.GREEN}✅ Saved to KB.{C.RESET}")
                else:
                    print(f"  {C.YELLOW}⚠  {res}{C.RESET}")
            return
    print(f"  {C.YELLOW}No match and no AI. Run  nova add  to save a fix manually.{C.RESET}")


# ── nova ask / nova -a ───────────────────────────────────────────────────────

def cmd_ask(config, query=None):
    """nova ask [question] / nova -a [question] — Ask Nova AI a direct question."""
    ai_config = get_active_ai_config()
    if not ai_config:
        print(f"  {C.RED}❌ No AI provider configured. Run:  nova add-llm{C.RESET}")
        return
    if not query or not query.strip():
        try:
            query = input(f"  {C.BOLD}Your question:{C.RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            return
    if not query:
        print(f"  {C.YELLOW}⚠  No question entered.{C.RESET}")
        return
    print(f"\n  {C.CYAN}🤖 Asking AI...{C.RESET}\n")
    answer = call_ai_ask(query, ai_config)
    if answer:
        print(f"  {C.GREEN}{answer.strip()}{C.RESET}\n")
    else:
        print(f"  {C.RED}No response from AI.{C.RESET}\n")


# ── nova solve ───────────────────────────────────────────────────────────────

def cmd_solve(config):
    """nova solve — Review last command output and add a custom fix."""
    print(f"\n  {C.ORANGE}{C.BOLD}📋 Nova — Solve & Add Fix{C.RESET}\n")
    raw = get_terminal_output()
    if not raw:
        print(f"  {C.YELLOW}⚠  No input. Paste an error or run a command first.{C.RESET}")
        return
    error_sig = detect_error(raw) or raw.strip()[:250]
    print(f"  {C.GREEN}Error:{C.RESET} {error_sig}\n")
    kb_path = get_active_kb_path()
    if not kb_path or not os.path.isdir(kb_path):
        print(f"  {C.RED}❌ Active KB not configured. Run:  nova setup{C.RESET}")
        return
    try:
        solution = input(f"  {C.BOLD}Solution (1 sentence):{C.RESET} ").strip()
        if not solution:
            print(f"  {C.YELLOW}Cancelled.{C.RESET}")
            return
        command = input(f"  {C.BOLD}Fix command (optional, Enter to skip):{C.RESET} ").strip()
    except (EOFError, KeyboardInterrupt):
        return
    ok, result = add_entry(kb_path, error_sig, solution, command, config.get("added_by", "unknown"))
    if ok:
        print(f"  {C.GREEN}✅ Fix saved to KB.{C.RESET}")
        display_solution(result, source="KB")
    else:
        print(f"  {C.YELLOW}⚠  {result}{C.RESET}")


# ── nova log ─────────────────────────────────────────────────────────────────

def cmd_log(n=20):
    """nova log [n] — Show last n terminal (history) entries."""
    histfile = os.environ.get("HISTFILE", os.path.expanduser("~/.bash_history"))
    if not os.path.isfile(histfile):
        print(f"  {C.YELLOW}No history file found: {histfile}{C.RESET}")
        return
    try:
        with open(histfile, "r", encoding="utf-8", errors="replace") as fh:
            lines = [l.strip() for l in fh.readlines() if l.strip()]
    except OSError:
        print(f"  {C.RED}Could not read history.{C.RESET}")
        return
    last_n = lines[-int(n) :] if n else lines[-20:]
    print(f"\n  {C.ORANGE}{C.BOLD}📜 Last {len(last_n)} terminal entries{C.RESET}\n")
    for i, line in enumerate(last_n, 1):
        print(f"  {C.DIM}{i:3}.{C.RESET} {line}")
    print()


# ── nova kb list ─────────────────────────────────────────────────────────────

def cmd_kb_list():
    """nova kb list — List all solutions in the KB (table with ID)."""
    kb_path = get_active_kb_path()
    if not kb_path or not os.path.isdir(kb_path):
        print(f"  {C.RED}❌ Active KB not configured. Run:  nova setup{C.RESET}")
        return
    resolve_conflicts(kb_path)
    data = load_kb(kb_path)
    print(f"\n  {C.ORANGE}{C.BOLD}📚 Knowledge Base — {len(data)} entries{C.RESET}\n")
    print(f"  {C.DIM}{'ID':<5} {'Error':<50} {'Solution':<40}{C.RESET}")
    print(f"  {C.ORANGE}{'─' * 95}{C.RESET}")
    for i, entry in enumerate(data, 1):
        err = (entry.get("error", "") or "")[:48]
        sol = (entry.get("solution", "") or "")[:38]
        print(f"  {i:<5} {err:<50} {sol:<40}")
    print()


# ── nova kb rm <ID> ───────────────────────────────────────────────────────────

def cmd_kb_rm(entry_id):
    """nova kb rm <ID> — Delete a solution by its table ID."""
    if not entry_id:
        print(f"  {C.RED}❌ Usage:  nova kb rm <ID>{C.RESET}")
        return
    kb_path = get_active_kb_path()
    if not kb_path or not os.path.isdir(kb_path):
        print(f"  {C.RED}❌ Active KB not configured.{C.RESET}")
        return
    ok, reason = delete_entry(kb_path, entry_id)
    if ok:
        print(f"  {C.GREEN}✅ Entry {entry_id} removed from KB.{C.RESET}")
    else:
        print(f"  {C.RED}❌ {reason}{C.RESET}")


# ── nova kb search ──────────────────────────────────────────────────────────

def cmd_kb_search(query=None):
    """nova kb search [query] — Manual lookup test for any error."""
    kb_path = get_active_kb_path()
    if not kb_path or not os.path.isdir(kb_path):
        print(f"  {C.RED}❌ Active KB not configured. Run:  nova setup{C.RESET}")
        return
    if not query or not query.strip():
        try:
            query = input(f"  {C.BOLD}Error text to search:{C.RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            return
    if not query:
        print(f"  {C.YELLOW}⚠  No query.{C.RESET}")
        return
    resolve_conflicts(kb_path)
    data = load_kb(kb_path)
    results = fuzzy_search(query, data, threshold=60)
    print(f"\n  {C.ORANGE}{C.BOLD}🔍 Search: \"{query[:50]}...\"{C.RESET}\n" if len(query) > 50 else f"\n  {C.ORANGE}{C.BOLD}🔍 Search: \"{query}\"{C.RESET}\n")
    if not results:
        print(f"  {C.YELLOW}No matches (threshold 60%).{C.RESET}\n")
        return
    for entry, score in results[:10]:
        display_solution(entry, score=score, source="KB")


# ── nova kb path ──────────────────────────────────────────────────────────────

def cmd_kb_path(new_path=None):
    """nova kb path [path] — View or update the active KB path."""
    if new_path and new_path.strip():
        path = normalize_kb_path(new_path)
        path = os.path.abspath(path)
        if not os.path.isdir(path):
            os.makedirs(path, exist_ok=True)
        kb_file = os.path.join(path, "kb.json")
        if not os.path.exists(kb_file):
            with open(kb_file, "w", encoding="utf-8") as fh:
                json.dump([], fh, indent=2)
        cfg = load_config()
        kbs = load_kbs()
        active = (cfg or {}).get("active_kb", "main")
        kbs[active] = path
        save_kbs(kbs)
        print(f"  {C.GREEN}✅ KB path set to: {path}{C.RESET}")
        return
    items = list_all_kbs()
    active = next((i for i in items if i[2]), None)
    if not active:
        print(f"  {C.YELLOW}No active KB. Run:  nova setup  or  nova use-kb <nick>{C.RESET}")
        return
    full = os.path.join(active[1], "kb.json")
    print(f"\n  {C.BOLD}Active KB path:{C.RESET} {full}")
    print(f"  {C.DIM}Nickname: {active[0]}{C.RESET}\n")


# ── nova save <nick> ──────────────────────────────────────────────────────────

def cmd_save(nickname):
    """nova save <nick> — Save current LLM setup as a new profile."""
    if not nickname or not nickname.strip():
        print(f"  {C.RED}❌ Usage:  nova save <nickname>{C.RESET}")
        return
    if save_current_as_profile(nickname.strip()):
        print(f"  {C.GREEN}✅ Current provider saved as profile '{nickname.strip()}'. Use:  nova use {nickname.strip()}{C.RESET}")
    else:
        print(f"  {C.RED}❌ No active provider to save. Run:  nova add-llm  first.{C.RESET}")


# ── nova providers ───────────────────────────────────────────────────────────

def cmd_providers():
    """nova providers — List supported AI hosts (provider types)."""
    print(f"\n  {C.ORANGE}{C.BOLD}🤖 Supported AI Providers{C.RESET}\n")
    for p in AI_PROVIDERS:
        print(f"  {C.CYAN}  • {p}{C.RESET}")
    print()


# ── nova set-provider ────────────────────────────────────────────────────────

def cmd_set_provider():
    """nova set-provider — Interactively change AI host (switch by nickname)."""
    items = list_all_providers()
    if not items:
        print(f"  {C.YELLOW}No providers configured. Run:  nova add-llm{C.RESET}")
        return
    print(f"\n  {C.ORANGE}{C.BOLD}Switch AI Provider{C.RESET}\n")
    for i, (nick, info, is_active) in enumerate(items, 1):
        marker = "●" if is_active else "○"
        print(f"  {i}. {marker} {nick}  ({info.get('provider')}/{info.get('model')})")
    try:
        choice = input(f"\n  {C.BOLD}Number or nickname to switch to:{C.RESET} ").strip()
        if not choice:
            return
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(items):
                choice = items[idx - 1][0]
        cmd_use(choice)
    except (EOFError, KeyboardInterrupt):
        pass


# ── nova model <m> ───────────────────────────────────────────────────────────

def cmd_model(model=None):
    """nova model [m] — Update the active provider's model."""
    if not model or not model.strip():
        print(f"  {C.RED}❌ Usage:  nova model <model-name>{C.RESET}")
        return
    if set_active_provider_model(model.strip()):
        print(f"  {C.GREEN}✅ Model set to: {model.strip()}{C.RESET}")
    else:
        print(f"  {C.RED}❌ No active provider. Run:  nova use <nick>  or  nova add-llm{C.RESET}")


# ── nova apikey <k> ──────────────────────────────────────────────────────────

def cmd_apikey(key=None):
    """nova apikey [k] — Securely save the active provider's API key."""
    if key and key.strip():
        if set_active_provider_apikey(key.strip()):
            print(f"  {C.GREEN}✅ API key updated for active provider.{C.RESET}")
        else:
            print(f"  {C.RED}❌ No active provider. Run:  nova use <nick>  or  nova add-llm{C.RESET}")
        return
    try:
        import getpass as gp
        k = gp.getpass(prompt=f"  {C.BOLD}API key (hidden):{C.RESET} ")
        if k and set_active_provider_apikey(k):
            print(f"  {C.GREEN}✅ API key updated.{C.RESET}")
        elif not k:
            print(f"  {C.YELLOW}Cancelled.{C.RESET}")
        else:
            print(f"  {C.RED}❌ No active provider.{C.RESET}")
    except (EOFError, KeyboardInterrupt):
        print()


# ── nova list ───────────────────────────────────────────────────────────────

def cmd_list():
    """nova list — Show all saved KB paths and AI profile nicknames."""
    print(f"\n  {C.ORANGE}{C.BOLD}📋 Saved Paths & Profiles{C.RESET}\n")
    kbs = list_all_kbs()
    provs = list_all_providers()
    print(f"  {C.BOLD}Knowledge Bases:{C.RESET}")
    if not kbs:
        print(f"  {C.DIM}  (none){C.RESET}")
    for nick, path, is_active in kbs:
        m = " ●" if is_active else ""
        print(f"  {C.CYAN}  {nick}{m}{C.RESET}  {path}")
    print(f"  {C.BOLD}AI Profiles:{C.RESET}")
    if not provs:
        print(f"  {C.DIM}  (none){C.RESET}")
    for nick, info, is_active in provs:
        m = " ●" if is_active else ""
        print(f"  {C.CYAN}  {nick}{m}{C.RESET}  ({info.get('provider')}/{info.get('model')})")
    print()


# ── nova init ────────────────────────────────────────────────────────────────

def cmd_init():
    """nova init — Run the configuration wizard (alias for setup)."""
    cmd_setup()


# ── nova config ──────────────────────────────────────────────────────────────

def cmd_config():
    """nova config — Show full active configuration and Active Environment."""
    cfg = load_config()
    if not cfg:
        print(f"  {C.YELLOW}Nova not configured. Run:  nova setup{C.RESET}")
        return
    print()
    _active_env()
    print(f"  {C.BOLD}User (added_by):{C.RESET} {cfg.get('added_by', '—')}")
    print(f"  {C.BOLD}Active KB nick:{C.RESET} {cfg.get('active_kb', '—')}")
    print(f"  {C.BOLD}Active AI nick:{C.RESET} {cfg.get('active_provider', '—')}\n")


# ── nova fresh ───────────────────────────────────────────────────────────────

def cmd_fresh():
    """nova fresh — Wipe all settings and start over."""
    print(f"\n  {C.RED}{C.BOLD}⚠  This will delete all Nova config, providers, and KB links.{C.RESET}")
    if not _ask_yn("Type yes to confirm", default_yes=False):
        print(f"  {C.DIM}Cancelled.{C.RESET}")
        return
    try:
        confirm = input(f"  {C.YELLOW}Type 'fresh' to confirm:{C.RESET} ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return
    if confirm != "fresh":
        print(f"  {C.DIM}Cancelled.{C.RESET}")
        return
    if reset_all_config():
        print(f"  {C.GREEN}✅ All settings wiped. Run  nova setup  to configure again.{C.RESET}")
    else:
        print(f"  {C.RED}❌ Could not remove some files.{C.RESET}")


# ── nova help ────────────────────────────────────────────────────────────────

def cmd_help():
    """nova help — Print full docs (table + Active Environment). Prompts for setup if first run."""
    print(BANNER)
    print(f"  {C.ORANGE}{C.BOLD}Commands{C.RESET}\n")
    # Table format: Category | Command | Description (match reference image)
    sep = f"  {C.ORANGE}{'─' * 78}{C.RESET}"
    print(f"  {C.BOLD}{'Category':<12} {'Command':<24} {'Description':<38}{C.RESET}")
    print(sep)
    print(f"  {'Support':<12} {'nova up':<24} {'Solves last terminal error (KB → AI).':<38}")
    print(f"  {'':<12} {'nova fix':<24} {'Paste error, get solution instantly.':<38}")
    print(f"  {'':<12} {'nova ask / -a':<24} {'Ask Nova AI a direct question.':<38}")
    print(f"  {'':<12} {'nova solve':<24} {'Review history, add custom fixes.':<38}")
    print(f"  {'':<12} {'nova log [n]':<24} {'Show last n terminal entries.':<38}")
    print(sep)
    print(f"  {'Knowledge':<12} {'nova add':<24} {'Manually add one error pattern.':<38}")
    print(f"  {'':<12} {'nova kb list':<24} {'Display all solutions (table with ID).':<38}")
    print(f"  {'':<12} {'nova kb rm <ID>':<24} {'Delete a solution by table ID.':<38}")
    print(f"  {'':<12} {'nova kb search':<24} {'Manual lookup test for any error.':<38}")
    print(f"  {'':<12} {'nova kb path':<24} {'View or update KB storage path.':<38}")
    print(sep)
    print(f"  {'AI / LLM':<12} {'nova save <nick>':<24} {'Save current LLM setup as profile.':<38}")
    print(f"  {'':<12} {'nova use <nick>':<24} {'Switch to a saved profile.':<38}")
    print(f"  {'':<12} {'nova providers':<24} {'List all supported AI hosts.':<38}")
    print(f"  {'':<12} {'nova set-provider':<24} {'Change the AI host (interactive).':<38}")
    print(f"  {'':<12} {'nova model <m>':<24} {'Update model (e.g. gpt-4o, sonnet).':<38}")
    print(f"  {'':<12} {'nova apikey <k>':<24} {'Securely save provider API key.':<38}")
    print(f"  {'':<12} {'nova add-llm':<24} {'Add a new AI provider.':<38}")
    print(f"  {'':<12} {'nova rm <nick>':<24} {'Remove a provider profile.':<38}")
    print(sep)
    print(f"  {'System':<12} {'nova list':<24} {'Show all paths and profile nicks.':<38}")
    print(f"  {'':<12} {'nova rm <n/idx>':<24} {'Delete profile nick or path.':<38}")
    print(f"  {'':<12} {'nova init':<24} {'Run the configuration wizard.':<38}")
    print(f"  {'':<12} {'nova config':<24} {'Show full active configuration.':<38}")
    print(f"  {'':<12} {'nova fresh':<24} {'Wipe all settings, start over.':<38}")
    print(f"  {'':<12} {'nova help':<24} {'Show this guide.':<38}")
    print(sep)
    print(f"  {C.ORANGE}  Workflow{C.RESET}  Run any command → if it fails →  nova up  → KB search → AI fallback")
    print()
    _active_env()
    # First-time: prompt for setup if no config or no active KB
    cfg = load_config()
    if not cfg or not cfg.get("active_kb"):
        print(f"  {C.GREEN}💡 First time? Run  nova setup  to set KB path and AI provider.{C.RESET}")
        try:
            ans = input(f"  {C.YELLOW}Run setup now? [Y/n]: {C.RESET}").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if ans in ("", "y", "yes"):
            print()
            cmd_setup()
        else:
            print()


def cmd_version():
    """nova version — Show Nova version."""
    print(f"\n  {C.BOLD}Nova CLI{C.RESET}  {C.CYAN}v{VERSION}{C.RESET}\n")


def cmd_reload():
    """nova reload — Instruction to refresh shell."""
    shell = os.path.basename(os.environ.get("SHELL", "bash"))
    rc_file = "~/.bashrc" if "bash" in shell else "~/.zshrc"
    cmd = f"source {rc_file}"
    
    # Try to copy to clipboard (WSL specific)
    copied = False
    try:
        subprocess.run(f'echo "{cmd}" | clip.exe', shell=True, check=True, stderr=subprocess.DEVNULL)
        copied = True
    except:
        pass

    print(f"\n  {C.BLUE}{C.BOLD}🔄 Refresh Terminal Session{C.RESET}")
    print(f"  {C.DIM}Your shell configuration has changed.{C.RESET}\n")
    
    if copied:
        print(f"  {C.GREEN}📋 Command copied to clipboard!{C.RESET}")
        print(f"  Just paste (Ctrl+V or Right-click) and hit Enter.\n")
    else:
        print(f"  {C.YELLOW}Please run:{C.RESET}")
        print(f"  {C.BOLD}{C.CYAN}{cmd}{C.RESET}\n")

    print(f"  {C.DIM}Tip: You can now use the shortcut:{C.RESET} {C.BOLD}nova-r{C.RESET}")


# ═══════════════════════════════════════════════════════════════════════════════

#  HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _show_available_providers():
    items = list_all_providers()
    if items:
        print(f"  {C.DIM}Available providers:{C.RESET}")
        for nick, _, is_active in items:
            marker = "●" if is_active else "○"
            print(f"  {C.DIM}  {marker} {nick}{C.RESET}")


# ═══════════════════════════════════════════════════════════════════════════════
#  DAILY ANNOUNCEMENTS (silent fetch on first run of the day)
# ═══════════════════════════════════════════════════════════════════════════════

def _maybe_show_announcements():
    """On first nova run each day: fetch announcements from repo and show new ones."""
    today = datetime.now().strftime("%Y-%m-%d")
    state_dir = os.path.dirname(ANNOUNCE_STATE_FILE)
    state = {}
    if os.path.exists(ANNOUNCE_STATE_FILE):
        try:
            with open(ANNOUNCE_STATE_FILE, "r", encoding="utf-8") as fh:
                state = json.load(fh)
        except (json.JSONDecodeError, OSError):
            pass
    if state.get("last_check_date") == today:
        return
    # Fetch announcements (silent on failure)
    try:
        req = urllib.request.Request(ANNOUNCEMENTS_URL)
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, OSError):
        state["last_check_date"] = today
        os.makedirs(state_dir, exist_ok=True)
        try:
            with open(ANNOUNCE_STATE_FILE, "w", encoding="utf-8") as fh:
                json.dump(state, fh, indent=2)
        except OSError:
            pass
        return
    announcements = data.get("announcements") or []
    seen = set(state.get("seen_ids") or [])
    to_show = [a for a in announcements if a.get("id") and a["id"] not in seen]
    if not to_show:
        state["last_check_date"] = today
        os.makedirs(state_dir, exist_ok=True)
        try:
            with open(ANNOUNCE_STATE_FILE, "w", encoding="utf-8") as fh:
                json.dump(state, fh, indent=2)
        except OSError:
            pass
        return
    # Show announcements clearly in the terminal
    print()
    print(f"  {C.ORANGE}╔══════════════════════════════════════════════════════╗{C.RESET}")
    print(f"  {C.ORANGE}║  {C.BOLD}📢  ANNOUNCEMENTS{C.ORANGE}                                    ║{C.RESET}")
    print(f"  {C.ORANGE}╠══════════════════════════════════════════════════════╣{C.RESET}")
    for a in to_show:
        title = a.get("title") or "Announcement"
        body = (a.get("body") or "").strip()
        print(f"  {C.ORANGE}║{C.RESET}  {C.BOLD}{C.ORANGE}{title}{C.RESET}")
        if body:
            for line in body.splitlines():
                print(f"  {C.ORANGE}║{C.RESET}  {line}")
        print(f"  {C.ORANGE}║{C.RESET}")
    print(f"  {C.ORANGE}╚══════════════════════════════════════════════════════╝{C.RESET}")
    print()
    state["last_check_date"] = today
    state["seen_ids"] = list(seen) + [a["id"] for a in to_show]
    os.makedirs(state_dir, exist_ok=True)
    try:
        with open(ANNOUNCE_STATE_FILE, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)
    except OSError:
        pass


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    """CLI dispatcher."""
    args = sys.argv[1:]

    # Daily announcements: first run of the day fetches and shows new ones
    _maybe_show_announcements()

    if not args:
        cmd_help()
        return

    command = args[0].lower()

    # ── Commands that don't need config ──────────────────────────────────
    if command in ("help", "-h", "--help"):
        cmd_help()
        return

    if command in ("version", "--v", "-v", "--version"):
        cmd_version()
        return

    if command in ("reload", "--r", "-r"):
        cmd_reload()
        return


    if command == "setup":
        cmd_setup()
        return

    if command == "add-llm":
        cmd_add_llm()
        return

    if command == "lp":
        cmd_lp()
        return

    if command == "cur":
        cmd_cur()
        return

    if command == "secrets-path":
        cmd_secrets_path()
        return

    if command == "test":
        target = args[1] if len(args) > 1 else None
        cmd_test(target)
        return

    if command == "rm":
        target = args[1] if len(args) > 1 else ""
        cmd_rm(target)
        return

    if command == "use":
        target = args[1] if len(args) > 1 else ""
        cmd_use(target)
        return

    if command == "lk":
        cmd_lk()
        return

    if command == "add-kb":
        nick = args[1] if len(args) > 1 else ""
        path = args[2] if len(args) > 2 else ""
        cmd_add_kb(nick, path)
        return

    if command == "rm-kb":
        target = args[1] if len(args) > 1 else ""
        cmd_rm_kb(target)
        return

    if command == "use-kb":
        target = args[1] if len(args) > 1 else ""
        cmd_use_kb(target)
        return

    if command == "cur-kb":
        cmd_cur_kb()
        return

    if command == "init":
        cmd_init()
        return

    if command == "config":
        cmd_config()
        return

    if command == "fresh":
        cmd_fresh()
        return

    if command == "list":
        cmd_list()
        return

    if command == "providers":
        cmd_providers()
        return

    if command == "set-provider":
        cmd_set_provider()
        return

    if command == "model":
        model_arg = args[1] if len(args) > 1 else None
        cmd_model(model_arg)
        return

    if command == "apikey":
        key_arg = args[1] if len(args) > 1 else None
        cmd_apikey(key_arg)
        return

    if command == "save":
        nick = args[1] if len(args) > 1 else ""
        cmd_save(nick)
        return

    if command == "kb":
        kb_sub = (args[1] if len(args) > 1 else "").lower()
        kb_rest = args[2:] if len(args) > 2 else []
        if kb_sub == "list":
            cmd_kb_list()
        elif kb_sub == "rm":
            cmd_kb_rm(kb_rest[0] if kb_rest else None)
        elif kb_sub == "search":
            cmd_kb_search(" ".join(kb_rest) if kb_rest else None)
        elif kb_sub == "path":
            cmd_kb_path(" ".join(kb_rest).strip() or None)
        else:
            print(f"  {C.RED}Usage:  nova kb list|rm|search|path [args]{C.RESET}")
        return

    if command == "log":
        n_arg = args[1] if len(args) > 1 else "20"
        try:
            n = int(n_arg) if n_arg else 20
        except ValueError:
            n = 20
        cmd_log(n)
        return

    # ── Commands that need config ────────────────────────────────────────

    config = get_config()
    if not config:
        return

    if command == "up":
        cmd_up(config)
    elif command == "add":
        cmd_add(config)
    elif command == "fix":
        cmd_fix(config)
    elif command in ("ask", "-a"):
        query = " ".join(args[1:]).strip() if len(args) > 1 else None
        cmd_ask(config, query)
    elif command == "solve":
        cmd_solve(config)
    else:
        print(f"  {C.RED}Unknown command: {command}{C.RESET}")
        print(f"  {C.DIM}Run  nova help  for usage.{C.RESET}")


if __name__ == "__main__":
    main()

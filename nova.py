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


from config import (
    add_provider_interactive,
    remove_provider,
    switch_provider,
    list_all_providers,
    get_active_ai_config,
    test_provider_connection,
    secrets_path,
    add_kb_source,
    remove_kb_source,
    switch_kb,
    list_all_kbs,
    get_active_kb_path,
)
from kb_manager import (
    fuzzy_search,
    load_kb,
    add_entry,
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


# ═══════════════════════════════════════════════════════════════════════════════
#  BANNER
# ═══════════════════════════════════════════════════════════════════════════════

BANNER = f"""{C.BLUE}{C.BOLD}
    ╔═══════════════════════════════════════════════╗
    ║   ███╗   ██╗  ██████╗  ██╗   ██╗  █████╗     ║
    ║   ████╗  ██║ ██╔═══██╗ ██║   ██║ ██╔══██╗    ║
    ║   ██╔██╗ ██║ ██║   ██║ ██║   ██║ ███████║    ║
    ║   ██║╚██╗██║ ██║   ██║ ╚██╗ ██╔╝ ██╔══██║    ║
    ║   ██║ ╚████║ ╚██████╔╝  ╚████╔╝  ██║  ██║    ║
    ║   ╚═╝  ╚═══╝  ╚═════╝    ╚═══╝   ╚═╝  ╚═╝    ║
    ║             Support Tool                     ║
    ╚═══════════════════════════════════════════════╝{C.RESET}
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


# ── nova help ────────────────────────────────────────────────────────────────

def cmd_help():
    """nova help — Print full docs."""
    print(BANNER)
    print(f"  {C.BOLD}USAGE{C.RESET}")
    print()
    print(f"  {C.CYAN}Error Resolution:{C.RESET}")
    print(f"    nova up                   Capture error → search KB → AI fallback")
    print(f"    nova add                  Save a new error solution to the KB")
    print()
    print(f"  {C.CYAN}KB Management:{C.RESET}")
    print(f"    nova add-kb <nick> <path> Add/Register a new KB folder")
    print(f"    nova rm-kb <nick>         Unlink a KB folder")
    print(f"    nova use-kb <nick>        Switch active Knowledge Base")
    print(f"    nova lk                   List all configured KBs")
    print(f"    nova cur-kb               Show current active KB & path")
    print()
    print(f"  {C.CYAN}AI Provider Management:{C.RESET}")
    print(f"    nova add-llm              Add a new AI provider")
    print(f"    nova rm <provider>        Remove a provider")
    print(f"    nova use <provider>       Switch active AI provider")
    print(f"    nova lp                   List all configured providers")
    print(f"    nova cur                  Show current active provider")
    print(f"    nova test [provider]      Test AI connection")
    print()
    print(f"  {C.CYAN}Configuration:{C.RESET}")
    print(f"    nova setup                First-time setup (KB path + AI)")
    print(f"    nova version              Show version info")
    print(f"    nova secrets-path         Show secrets file location")
    print(f"    nova help                 Show this help message")
    print()
    print(f"  {C.BOLD}EXAMPLES{C.RESET}")
    print(f"    {C.DIM}# Auto-capture from terminal{C.RESET}")
    print(f"    $ nova up")
    print()
    print(f"    {C.DIM}# Pipe error output directly{C.RESET}")
    print(f"    $ python3 app.py 2>&1 | nova up")
    print()
    print(f"    {C.DIM}# Add a fix you just discovered{C.RESET}")
    print(f"    $ nova add")
    print()
    print(f"    {C.DIM}# Add OpenAI as a second provider{C.RESET}")
    print(f"    $ nova add-llm")
    print()
    print(f"    {C.DIM}# Switch to a different provider{C.RESET}")
    print(f"    $ nova use openai-gpt4")
    print()
    print(f"  {C.BOLD}PROTOCOLS{C.RESET}")
    print(f"    {C.CYAN}Error Intercept{C.RESET}    — nova up scans, searches, suggests")
    print(f"    {C.CYAN}Knowledge Capture{C.RESET}  — nova add sanitizes and saves")
    print(f"    {C.CYAN}Safety & Privacy{C.RESET}   — auto-redacts IPs, keys, paths")
    print(f"    {C.CYAN}Verification{C.RESET}       — re-runs fix, confirms success")
    print()


def cmd_version():
    """nova version — Show Nova version."""
    print(f"\n  {C.BOLD}Nova CLI{C.RESET}  {C.CYAN}v{VERSION}{C.RESET}\n")


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
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    """CLI dispatcher."""
    args = sys.argv[1:]

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

    # ── Commands that need config ────────────────────────────────────────

    config = get_config()
    if not config:
        return

    if command == "up":
        cmd_up(config)
    elif command == "add":
        cmd_add(config)
    else:
        print(f"  {C.RED}Unknown command: {command}{C.RESET}")
        print(f"  {C.DIM}Run  nova help  for usage.{C.RESET}")


if __name__ == "__main__":
    main()

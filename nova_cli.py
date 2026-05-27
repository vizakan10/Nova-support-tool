#!/usr/bin/env python3
"""
Nova CLI — Framework Reliability Agent
Main entry point for all nova commands.
"""

import os
import re
import sys
import json
import time
import shutil
import threading
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
    NOVA_HTTP_USER_AGENT,
)
from kb_manager import (
    fuzzy_search,
    load_kb,
    load_kb_for_write,
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

# Keywords/phrases that indicate an error line (used to detect errors in pasted output).
# When a line matches any pattern, it is considered an error signature for KB search.
_ERROR_PATTERNS = [
    re.compile(r"(?i)Traceback \(most recent call last\)"),
    re.compile(r"(?i)(ModuleNotFoundError|ImportError|FileNotFoundError|PermissionError)"),
    re.compile(r"(?i)(SyntaxError|TypeError|ValueError|KeyError|AttributeError|NameError)"),
    re.compile(r"(?i)(RuntimeError|OSError|IOError|ConnectionError|TimeoutError)"),
    re.compile(r"(?i)(npm ERR!|Error:|ERR_|ENOENT|EACCES|ENOSPC|ECONNREFUSED)"),
    re.compile(r"(?i)(FATAL|PANIC|ABORT|SEGFAULT|core dumped)"),
    re.compile(r"(?i)(command not found|no such file|permission denied)"),
    re.compile(r"(?i)(BUILD FAILED|COMPILATION ERROR|LINK ERROR)"),
    re.compile(r"=>\s*ERROR\s+\["),   # Docker build: => ERROR [stage-0 8/19] RUN ...
    re.compile(r"(?i)\bERROR\s+\["),  # Docker: ERROR [stage-0] RUN … (no =>)
    re.compile(r"(?i)(failed|error|exception|denied|crash)"),
    re.compile(r"\b(401|403|404|500|502|503)\b"),
]


# ═══════════════════════════════════════════════════════════════════════════════
#  TERMINAL OUTPUT CAPTURE
# ═══════════════════════════════════════════════════════════════════════════════

def _nova_session_dir():
    """Hook session directory for the parent shell (matches nova_hooks.sh $$)."""
    env_dir = os.environ.get("NOVA_SESSION_DIR", "").strip()
    if env_dir:
        return env_dir

    ppid = os.getppid()
    if os.path.isdir("/dev/shm") and os.access("/dev/shm", os.W_OK):
        return f"/dev/shm/nova_{ppid}"

    return os.path.join(os.path.expanduser("~/.nova/session"), f"nova_{ppid}")


_HOOKS_FILE = os.path.expanduser("~/.nova/nova_hooks.sh")
_HOOKS_SOURCE_LINE = "source ~/.nova/nova_hooks.sh"


def _hooks_source_line_in_bashrc():
    bashrc = os.path.expanduser("~/.bashrc")
    try:
        with open(bashrc, "r", encoding="utf-8", errors="replace") as fh:
            return _HOOKS_SOURCE_LINE in fh.read()
    except OSError:
        return False


def _hooks_installed():
    return os.path.isfile(_HOOKS_FILE)


def _print_hooks_inactive_help():
    """Explain why capture failed and how to activate hooks in this terminal."""
    if _hooks_installed() and _hooks_source_line_in_bashrc():
        print(
            f"  {C.YELLOW}⚠  Hooks are installed but not loaded in this terminal.{C.RESET}"
        )
        print(
            f"  {C.DIM}   Run:  source ~/.bashrc{C.RESET}"
        )
        print(
            f"  {C.DIM}   Or:   source ~/.nova/nova_hooks.sh{C.RESET}"
        )
        print(
            f"  {C.DIM}   Then re-run your failing command and try  nova up  again.{C.RESET}"
        )
    elif _hooks_installed():
        print(
            f"  {C.YELLOW}⚠  Hooks file exists but ~/.bashrc does not source it.{C.RESET}"
        )
        print(f"  {C.DIM}   Run:  nova install-hooks{C.RESET}")
    else:
        print(
            f"  {C.YELLOW}⚠  Nova shell hooks are not installed.{C.RESET}"
        )
        print(
            f"  {C.DIM}   Run:  nova install-hooks  then  source ~/.bashrc{C.RESET}"
        )


_PASSWORD_CMD_BLOCKLIST = frozenset({
    "docker", "python", "python3", "node", "npm", "git", "make", "gradle",
    "kubectl", "bash", "sh", "sudo", "apt", "pip", "curl", "wget", "ls", "cd",
    "cat", "grep", "vim", "nano", "false", "true",
})


def _cmd_looks_like_password(cmd):
    """True if cmd looks like an accidental bare password entry (no spaces)."""
    if not cmd or " " in cmd:
        return False
    if len(cmd) < 8 or len(cmd) > 30:
        return False
    if cmd.lower() in _PASSWORD_CMD_BLOCKLIST:
        return False
    if not re.search(r"[A-Za-z]", cmd):
        return False
    if not re.search(r"\d", cmd):
        return False
    return bool(re.match(r"^[A-Za-z0-9@#$!_%^&*]+$", cmd))


def _clear_session_sensitive(session_dir):
    """Clear captured command/exit files after a suspected password entry."""
    for name in ("last_cmd", "last_exit"):
        path = os.path.join(session_dir, name)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("")
        except OSError:
            pass


def get_terminal_output():
    """
    Capture text for KB / AI from Nova shell hooks.

    **Piped stdin (optional):** forward one command's output explicitly.
    """
    if not sys.stdin.isatty():
        data = sys.stdin.read()
        if data.strip():
            return data.strip()

    captured = _try_hook_capture()
    if captured[0]:
        return captured[0][0]
    return None


def _read_session_file(session_dir, name):
    path = os.path.join(session_dir, name)
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def _read_last_output(session_dir, max_wait=0.4, interval=0.05):
    """Read last_output; brief retry while tee/process substitution flushes."""
    path = os.path.join(session_dir, "last_output")
    deadline = time.monotonic() + max_wait
    prev_size = None
    content = ""

    while True:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read()
            size = os.path.getsize(path)
            if prev_size is not None and size == prev_size:
                return content
            prev_size = size
        except OSError:
            content = ""

        if time.monotonic() >= deadline:
            return content
        time.sleep(interval)


_OUTPUT_NOT_CAPTURED = (
    "(Note: command output was not captured by shell hooks. "
    "Diagnosis will use the command only.)"
)


def _try_hook_capture(quiet=False, silent=False):
    """Read last command and output captured by nova_hooks.sh (no command re-run).

    Returns ``((combined_text, last_cmd), None)`` on success, or
    ``(None, reason)`` on failure where *reason* is one of:
    ``inactive``, ``no_cmd``, ``password``.

    When *silent* is True, do not print diagnostics (for use under a spinner).
    """
    session_dir = _nova_session_dir()

    if not os.path.isdir(session_dir):
        if not silent:
            _print_hooks_inactive_help()
        return None, "inactive"

    last_cmd = _read_session_file(session_dir, "last_cmd").strip()
    if not last_cmd:
        if not silent:
            print(f"  {C.YELLOW}⚠  No captured command found.{C.RESET}")
            print(
                f"  {C.DIM}   Run a failing command in this terminal, then  nova up{C.RESET}"
            )
        return None, "no_cmd"

    if _cmd_looks_like_password(last_cmd):
        _clear_session_sensitive(session_dir)
        if not silent:
            print(
                f"  {C.YELLOW}Last command looks like a password and was cleared for safety. "
                f"Please re-run your failing command.{C.RESET}"
            )
        return None, "password"

    last_output = _read_last_output(session_dir).strip()
    if not last_output:
        if not silent:
            print(
                f"  {C.YELLOW}⚠  Command output was not captured; using command only.{C.RESET}"
            )
            print(
                f"  {C.DIM}   Re-run your failing command, then try  nova up  again.{C.RESET}"
            )
        combined = "\n".join([f"$ {last_cmd}", _OUTPUT_NOT_CAPTURED])
        return (combined, last_cmd), None

    if not quiet and not silent:
        print(f"  {C.DIM}Scanning:{C.RESET} {C.CYAN}{last_cmd}{C.RESET}")

    return ("\n".join([f"$ {last_cmd}", last_output]), last_cmd), None


def _prompt_paste():
    print(
        f"  {C.YELLOW}📋 Paste what the terminal showed (select text, paste, Ctrl+D when done):{C.RESET}"
    )
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


_TRUNCATE_MARKER = "... [truncated] ..."


def _truncate_for_ai(text, limit=3000, head=500, tail=2500):
    """Shrink large output before sending to AI (keeps head + tail)."""
    if not text or len(text) <= limit:
        return text
    return text[:head] + _TRUNCATE_MARKER + text[-tail:]


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


_AI_SECRET_PATTERNS = [
    (re.compile(r"(?i)(token=)([^\s'\"]+)"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(password=)([^\s'\"]+)"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(api_key=)([^\s'\"]+)"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(Bearer\s+)([^\s'\"]+)"), r"\1[REDACTED]"),
    (re.compile(r"ghp_[A-Za-z0-9]+"), "[REDACTED]"),
    (re.compile(r"sk-[A-Za-z0-9]+"), "[REDACTED]"),
]


def _redact_for_ai(text):
    """Sanitize and redact sensitive patterns before sending error text to AI."""
    text = sanitize(text)
    for pattern, repl in _AI_SECRET_PATTERNS:
        text = pattern.sub(repl, text)
    return text


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

    prompt = _AI_PROMPT.format(error=_redact_for_ai(error_text))

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

    headers["User-Agent"] = NOVA_HTTP_USER_AGENT
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


def _parse_ai_response(ai_text):
    """Parse Solution:/Command: lines from AI text."""
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


def _extract_stream_delta(chunk, provider):
    if provider == "claude":
        if chunk.get("type") == "content_block_delta":
            return chunk.get("delta", {}).get("text", "")
        return ""
    choices = chunk.get("choices") or []
    if choices:
        return choices[0].get("delta", {}).get("content", "") or ""
    return ""


def _stream_print_words(piece):
    """Print streamed text word-by-word for a live CLI feel."""
    if not piece:
        return
    tokens = re.split(r"(\s+)", piece)
    for tok in tokens:
        if not tok:
            continue
        sys.stdout.write(tok)
        if tok.strip():
            sys.stdout.flush()


def call_ai_stream(error_text, ai_config):
    """Call AI with streaming; print response word-by-word. Returns parsed result dict."""
    provider = ai_config.get("provider", "")
    api_key = ai_config.get("api_key", "")
    model = ai_config.get("model", "")
    endpoint = ai_config.get("endpoint", "")

    if not all([provider, api_key, model, endpoint]):
        return None

    prompt = _AI_PROMPT.format(error=_redact_for_ai(error_text))

    if provider == "claude":
        body = {
            "model": model,
            "max_tokens": 300,
            "stream": True,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
    else:
        body = {
            "model": model,
            "stream": True,
            "messages": [
                {"role": "system", "content": "You are a concise DevOps assistant."},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 300,
            "temperature": 0.2,
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "Authorization": f"Bearer {api_key}",
        }

    headers["User-Agent"] = NOVA_HTTP_USER_AGENT
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(endpoint, data=payload, headers=headers)

    full_parts = []
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or line.startswith("event:"):
                    continue
                if line.startswith("data:"):
                    line = line[5:].strip()
                if line == "[DONE]":
                    break
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                piece = _extract_stream_delta(chunk, provider)
                if not piece:
                    continue
                full_parts.append(piece)
                _stream_print_words(piece)
        print()
    except urllib.error.HTTPError as exc:
        print()
        msg = exc.read().decode("utf-8", errors="replace")[:200]
        print(f"  {C.RED}⚠  AI API error ({exc.code}): {msg}{C.RESET}")
        return None
    except Exception as exc:
        print()
        print(f"  {C.RED}⚠  AI request failed: {exc}{C.RESET}")
        return None

    return _parse_ai_response("".join(full_parts))


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
    headers["User-Agent"] = NOVA_HTTP_USER_AGENT
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(endpoint, data=payload, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        msg = exc.read().decode("utf-8", errors="replace")[:400]
        print(f"  {C.RED}⚠  AI API error ({exc.code}): {msg}{C.RESET}")
        return None
    except Exception as exc:
        print(f"  {C.RED}⚠  AI request failed: {exc}{C.RESET}")
        return None
    if provider == "claude":
        return (data.get("content") or [{}])[0].get("text", "")
    return (data.get("choices") or [{}])[0].get("message", {}).get("content", "")


# ═══════════════════════════════════════════════════════════════════════════════
#  DISPLAY HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

_SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class _Spinner:
    """Lightweight terminal spinner (background thread)."""

    def __init__(self, message="Scanning..."):
        self.message = message
        self._stop = threading.Event()
        self._thread = None

    def __enter__(self):
        if hasattr(sys.stdout, "isatty") and sys.stdout.isatty():
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=0.5)
        if hasattr(sys.stdout, "isatty") and sys.stdout.isatty():
            sys.stdout.write("\r" + " " * (len(self.message) + 6) + "\r")
            sys.stdout.flush()
        return False

    def _spin(self):
        i = 0
        while not self._stop.is_set():
            frame = _SPINNER_FRAMES[i % len(_SPINNER_FRAMES)]
            sys.stdout.write(f"\r  {C.CYAN}{frame}{C.RESET}  {self.message}")
            sys.stdout.flush()
            i += 1
            self._stop.wait(0.08)


def _print_up_header(last_cmd):
    print()
    print(f"  {C.RED}✗{C.RESET}  {C.WHITE}{C.BOLD}{last_cmd}{C.RESET}")


def _print_up_kb_hit(entry):
    solution = entry.get("solution", "")
    command = entry.get("command", "")
    print()
    print(f"  {C.GREEN}⚡ Knowledge Base{C.RESET}")
    print()
    print(f"  {C.BOLD}Solution:{C.RESET} {solution}")
    if command:
        print(f"  {C.BOLD}Command:{C.RESET}  {C.CYAN}{command}{C.RESET}")
    return command


def _print_up_ai_intro():
    print()
    print(f"  {C.CYAN}⟳ Asking AI...{C.RESET}")
    print(f"  {C.DIM}{'─' * 44}{C.RESET}")
    sys.stdout.write("  ")
    sys.stdout.flush()


def _print_up_fix_lines(solution, command):
    print()
    print(f"  {C.BOLD}Solution:{C.RESET} {solution}")
    if command:
        print(f"  {C.BOLD}Command:{C.RESET}  {C.CYAN}{command}{C.RESET}")


def _print_done_footer(start_time):
    elapsed = time.monotonic() - start_time
    plain = f"Done in {elapsed:.1f}s"
    try:
        width = shutil.get_terminal_size((80, 20)).columns
    except OSError:
        width = 80
    pad = max(0, width - len(plain))
    print(f"{' ' * pad}{C.DIM}{plain}{C.RESET}")


def _run_command_up(command):
    if not command:
        return False
    try:
        ans = input(f"  {C.YELLOW}Run fix? [y/N]: {C.RESET}").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    if ans not in ("y", "yes"):
        return False
    print(f"  {C.DIM}$ {command}{C.RESET}")
    try:
        rc = subprocess.call(command, shell=True, executable="/bin/bash", timeout=120)
        if rc == 0:
            print(f"  {C.GREEN}✅ Command succeeded.{C.RESET}")
            return True
        print(f"  {C.RED}❌ Exited with code {rc}.{C.RESET}")
    except subprocess.TimeoutExpired:
        print(f"  {C.YELLOW}⚠  Command timed out.{C.RESET}")
    except Exception as exc:
        print(f"  {C.RED}❌ {exc}{C.RESET}")
    return False


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
    t0 = time.monotonic()
    try:
        kb_path = get_active_kb_path()
        if not kb_path or not os.path.isdir(kb_path):
            print(f"  {C.RED}❌ Active KB not found or not configured.{C.RESET}")
            print(f"  {C.DIM}   Run:  nova setup  or  nova use-kb <nickname>{C.RESET}")
            return

        raw = None
        last_cmd = ""
        error_sig = ""
        results = []
        merged = 0
        capture_reason = None

        with _Spinner("Scanning..."):
            merged = resolve_conflicts(kb_path)
            captured, capture_reason = _try_hook_capture(quiet=True, silent=True)
            if captured:
                raw, last_cmd = captured
            if raw:
                error_sig = detect_error(raw) or raw.strip()[:250]
                kb_data = load_kb(kb_path)
                results = fuzzy_search(error_sig, kb_data, threshold=70)

        if not raw:
            if capture_reason == "inactive":
                _print_hooks_inactive_help()
            elif capture_reason == "no_cmd":
                print(f"  {C.YELLOW}⚠  No captured command found.{C.RESET}")
                print(
                    f"  {C.DIM}   Run a failing command in this terminal, then  nova up{C.RESET}"
                )
            elif capture_reason == "password":
                print(
                    f"  {C.YELLOW}Last command looks like a password and was cleared for safety. "
                    f"Please re-run your failing command.{C.RESET}"
                )
            return

        _print_up_header(last_cmd)

        if merged:
            print(f"  {C.DIM}Merged {merged} OneDrive conflict entries.{C.RESET}")

        if results:
            best_entry, _best_score = results[0]
            cmd = _print_up_kb_hit(best_entry)
            _run_command_up(cmd)
            if len(results) > 1:
                print(f"\n  {C.DIM}Other matches:{C.RESET}")
                for entry, sc in results[1:3]:
                    print(f"  {C.DIM}  • ({sc}%) {entry.get('error', '')[:60]}{C.RESET}")
            return

        ai_config = get_active_ai_config()
        if not ai_config:
            print(f"\n  {C.RED}No AI provider configured. Run: nova setup{C.RESET}")
            print(f"  {C.DIM}Tip: run  nova add  to save a fix for your team.{C.RESET}")
            return

        _print_up_ai_intro()
        ai_result = call_ai_stream(_truncate_for_ai(raw), ai_config)
        streamed = ai_result is not None
        if ai_result is None:
            ai_result = call_ai(_truncate_for_ai(raw), ai_config)
        if ai_result and ai_result.get("solution"):
            if not streamed:
                _print_up_fix_lines(ai_result["solution"], ai_result.get("command", ""))
            _run_command_up(ai_result.get("command", ""))
            if _ask_yn("Save fix to KB?", default_yes=False):
                ok, res = add_entry(
                    kb_path,
                    error_sig,
                    ai_result["solution"],
                    ai_result.get("command", ""),
                    config.get("added_by", "unknown"),
                )
                if ok:
                    print(f"  {C.GREEN}✅ Saved to KB.{C.RESET}")
                else:
                    print(f"  {C.YELLOW}⚠  {res}{C.RESET}")
            return
        print(f"  {C.YELLOW}⚠  AI couldn't provide a solution.{C.RESET}")
        print(f"  {C.DIM}Tip: run  nova add  to save a fix for your team.{C.RESET}")
    finally:
        _print_done_footer(t0)


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
    cfg = interactive_setup()
    if cfg is not None and not (_hooks_installed() and _hooks_source_line_in_bashrc()):
        print(f"\n  {C.DIM}▶ Installing shell hooks...{C.RESET}")
        cmd_install_hooks()


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


def _find_nova_hooks_source():
    """Locate nova_hooks.sh from repo, editable install, or pip data_files."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "nova_hooks.sh"),
        os.path.join(sys.prefix, "share", "nova-cli", "nova_hooks.sh"),
        os.path.join(os.path.expanduser("~/.local"), "share", "nova-cli", "nova_hooks.sh"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def cmd_install_hooks():
    """nova install-hooks — Install shell hooks for output capture."""
    import shutil

    source = _find_nova_hooks_source()
    if not source:
        print(f"  {C.RED}❌ nova_hooks.sh not found in the installation.{C.RESET}")
        print(f"  {C.DIM}   Reinstall Nova from the repo, then try again.{C.RESET}")
        return

    dest_dir = os.path.dirname(CONFIG_FILE)
    dest = os.path.join(dest_dir, "nova_hooks.sh")
    try:
        os.makedirs(dest_dir, exist_ok=True)
        shutil.copy2(source, dest)
        with open(dest, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read()
        with open(dest, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content.replace("\r", ""))
    except OSError as exc:
        print(f"  {C.RED}❌ Could not install hooks: {exc}{C.RESET}")
        return

    bashrc = os.path.expanduser("~/.bashrc")
    hook_line = "source ~/.nova/nova_hooks.sh"
    already = False
    if os.path.isfile(bashrc):
        try:
            with open(bashrc, "r", encoding="utf-8", errors="replace") as fh:
                already = hook_line in fh.read()
        except OSError:
            pass

    if not already:
        try:
            with open(bashrc, "a", encoding="utf-8") as fh:
                fh.write("\n# Nova CLI shell hooks\n")
                fh.write(f"{hook_line}\n")
        except OSError as exc:
            print(f"  {C.RED}❌ Could not update ~/.bashrc: {exc}{C.RESET}")
            print(f"  {C.DIM}   Add manually:  {hook_line}{C.RESET}")
            return

    print(
        f"\n  {C.GREEN}Hooks installed.{C.RESET} "
        f"{C.DIM}One-time: open a new terminal (or run{C.RESET} "
        f"{C.CYAN}source ~/.bashrc{C.RESET}{C.DIM}).{C.RESET}"
    )
    print(
        f"  {C.DIM}After that, hooks load automatically every time you open a terminal.{C.RESET}\n"
    )


def cmd_debug_session():
    """nova debug-session — Print hook capture state (testing only)."""
    session_dir = _nova_session_dir()
    exists = os.path.isdir(session_dir)
    env_dir = os.environ.get("NOVA_SESSION_DIR", "").strip()

    print(f"\n  {C.ORANGE}{C.BOLD}🔬 Nova — debug-session (testing only){C.RESET}\n")
    print(f"  {C.BOLD}Parent PID:{C.RESET} {os.getppid()}")
    print(f"  {C.BOLD}Session dir:{C.RESET} {session_dir}")
    if env_dir:
        print(f"  {C.BOLD}NOVA_SESSION_DIR:{C.RESET} {env_dir}")
    print(f"  {C.BOLD}Exists:{C.RESET} {'yes' if exists else 'no'}")

    capture_log = os.path.join(session_dir, "capture.log")
    if exists and os.path.isfile(capture_log):
        try:
            print(f"  {C.BOLD}capture.log:{C.RESET} {os.path.getsize(capture_log)} bytes")
        except OSError:
            pass
    print()

    for name in ("last_cmd", "last_output"):
        path = os.path.join(session_dir, name)
        print(f"  {C.BOLD}{name}:{C.RESET}")
        if not exists or not os.path.isfile(path):
            print(f"  {C.DIM}(missing){C.RESET}\n")
            continue
        try:
            content = _read_session_file(session_dir, name)
            if content:
                print(content, end="" if content.endswith("\n") else "\n")
            else:
                print(f"  {C.DIM}(empty){C.RESET}\n")
                continue
        except OSError as exc:
            print(f"  {C.RED}read error: {exc}{C.RESET}\n")
            continue
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
    data, kb_err = load_kb_for_write(kb_path)
    if kb_err:
        print(f"  {C.RED}❌ {kb_err}{C.RESET}")
        return
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
    data, kb_err = load_kb_for_write(kb_path)
    if kb_err:
        print(f"  {C.RED}❌ {kb_err}{C.RESET}")
        return
    results = fuzzy_search(query, data, threshold=60)
    print(f"\n  {C.ORANGE}{C.BOLD}🔍 Search: \"{query[:50]}...\"{C.RESET}\n" if len(query) > 50 else f"\n  {C.ORANGE}{C.BOLD}🔍 Search: \"{query}\"{C.RESET}\n")
    if not results:
        print(f"  {C.YELLOW}No matches (threshold 60%).{C.RESET}\n")
        return
    for entry, score in results[:10]:
        display_solution(entry, score=score, source="KB")


# ── nova search ──────────────────────────────────────────────────────────────

def cmd_search(config, query=None):
    """nova search [query] — Ask anything; KB first, AI fallback."""
    kb_path = get_active_kb_path()
    if not kb_path or not os.path.isdir(kb_path):
        print(f"  {C.RED}❌ Active KB not configured. Run:  nova setup{C.RESET}")
        return

    if not query or not query.strip():
        try:
            query = input(f"  {C.BOLD}Search: {C.RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            return
    if not query:
        print(f"  {C.YELLOW}⚠  No query.{C.RESET}")
        return

    print(f"\n  {C.ORANGE}{C.BOLD}🔍 \"{query}\"{C.RESET}\n")

    resolve_conflicts(kb_path)
    data, kb_err = load_kb_for_write(kb_path)
    if kb_err:
        print(f"  {C.RED}❌ {kb_err}{C.RESET}")
        return

    results = fuzzy_search(query, data, threshold=55)
    if results:
        print(f"  {C.GREEN}⚡ Knowledge Base  {C.DIM}({len(results)} match{'es' if len(results) > 1 else ''}){C.RESET}\n")
        for entry, score in results[:5]:
            solution = entry.get("solution", "")
            command  = entry.get("command", "")
            error    = entry.get("error", "")
            print(f"  {C.BOLD}{error[:70]}{C.RESET}")
            print(f"  {C.DIM}→{C.RESET} {solution}")
            if command:
                print(f"  {C.BOLD}Command:{C.RESET} {C.CYAN}{command}{C.RESET}")
            print(f"  {C.DIM}Match: {score}%{C.RESET}")
            print()
        best_cmd = results[0][0].get("command", "")
        if best_cmd:
            _run_command_up(best_cmd)
        return

    # No KB match — ask AI
    ai_config = get_active_ai_config()
    if not ai_config:
        print(f"  {C.YELLOW}No KB matches and no AI configured. Run:  nova setup{C.RESET}")
        return

    print(f"  {C.CYAN}⟳ Not in KB — asking AI...{C.RESET}")
    print(f"  {C.DIM}{'─' * 44}{C.RESET}")
    sys.stdout.write("  ")
    sys.stdout.flush()
    ai_result = call_ai_stream(query, ai_config)
    if ai_result is None:
        ai_result = call_ai(query, ai_config)
    if ai_result and ai_result.get("solution"):
        if not call_ai_stream:
            _print_up_fix_lines(ai_result["solution"], ai_result.get("command", ""))
        _run_command_up(ai_result.get("command", ""))
        if _ask_yn("Save to KB?", default_yes=False):
            ok, res = add_entry(
                kb_path, query,
                ai_result["solution"],
                ai_result.get("command", ""),
                config.get("added_by", "unknown"),
            )
            print(f"  {C.GREEN}✅ Saved.{C.RESET}" if ok else f"  {C.YELLOW}⚠  {res}{C.RESET}")
        return
    print(f"  {C.YELLOW}⚠  AI couldn't answer. Try  nova ask  for a direct question.{C.RESET}")


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
    print(f"  {'':<12} {'nova search [q]':<24} {'Ask anything — KB first, AI fallback.':<38}")
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
    print(f"  {'System':<12} {'nova ano':<24} {'See the latest announcements.':<38}")
    print(f"  {'':<12} {'nova list':<24} {'Show all paths and profile nicks.':<38}")
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


def _fetch_announcements():
    """Fetch announcements from the repo. Returns list of announcements or None on failure.
    Tries remote URL first; on 404/network error falls back to local announcements.json
    (current directory or next to this script) so e.g. running from the repo works."""
    try:
        req = urllib.request.Request(ANNOUNCEMENTS_URL)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("announcements") or []
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, OSError):
        pass
    # Fallback: local file (e.g. when URL 404s or default branch isn't main)
    for path in [
        os.path.join(os.getcwd(), "announcements.json"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "announcements.json"),
    ]:
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                return data.get("announcements") or []
            except (json.JSONDecodeError, OSError):
                pass
    return None


def cmd_ano():
    """nova ano — Fetch and show the latest announcements."""
    print(f"\n  {C.ORANGE}{C.BOLD}📢  Fetching latest announcements...{C.RESET}\n")
    announcements = _fetch_announcements()
    if announcements is None:
        print(f"  {C.YELLOW}Could not load announcements (network or server).{C.RESET}\n")
        return
    if not announcements:
        print(f"  {C.DIM}No announcements at this time.{C.RESET}\n")
        return
    # Show newest first (by date if present)
    def sort_key(a):
        return (a.get("date") or "").strip(), (a.get("id") or "")
    announcements = sorted(announcements, key=sort_key, reverse=True)
    print(f"  {C.ORANGE}╔══════════════════════════════════════════════════════╗{C.RESET}")
    print(f"  {C.ORANGE}║  {C.BOLD}📢  ANNOUNCEMENTS{C.ORANGE}                                    ║{C.RESET}")
    print(f"  {C.ORANGE}╠══════════════════════════════════════════════════════╣{C.RESET}")
    for a in announcements:
        title = a.get("title") or "Announcement"
        date = (a.get("date") or "").strip()
        if date:
            title = f"{title}  ({date})"
        body = (a.get("body") or "").strip()
        print(f"  {C.ORANGE}║{C.RESET}  {C.BOLD}{C.ORANGE}{title}{C.RESET}")
        if body:
            for line in body.splitlines():
                print(f"  {C.ORANGE}║{C.RESET}  {line}")
        print(f"  {C.ORANGE}║{C.RESET}")
    print(f"  {C.ORANGE}╚══════════════════════════════════════════════════════╝{C.RESET}")
    print()


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

    if command in ("ano", "announcements"):
        cmd_ano()
        return

    if command in ("reload", "--r", "-r"):
        cmd_reload()
        return


    if command == "setup":
        cmd_setup()
        return

    if command == "install-hooks":
        cmd_install_hooks()
        return

    if command == "debug-session":
        cmd_debug_session()
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

    if command == "up":
        cmd_up(load_config() or {})
        return

    config = get_config()
    if not config:
        return

    if command == "add":
        cmd_add(config)
    elif command == "fix":
        cmd_fix(config)
    elif command in ("search", "s"):
        query = " ".join(args[1:]).strip() if len(args) > 1 else None
        cmd_search(config, query)
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

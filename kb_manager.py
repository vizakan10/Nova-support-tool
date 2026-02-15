#!/usr/bin/env python3
"""
Nova CLI — Knowledge Base Manager
Read/write kb.json, fuzzy search, conflict resolution, sanitization.
"""

import os
import re
import json
import glob
from difflib import SequenceMatcher
from datetime import datetime, timezone


# ═══════════════════════════════════════════════════════════════════════════════
#  SANITIZATION
# ═══════════════════════════════════════════════════════════════════════════════

# Compiled once at import time for performance
_SANITIZE_RULES = [
    # IPv4 addresses
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"), "[IP_REDACTED]"),
    # key=value or key: value where key looks like a secret
    (
        re.compile(
            r"(?i)(api[_-]?key|token|secret|password|auth|credential)"
            r"[\s]*[=:]\s*\S+"
        ),
        r"\1=[KEY_REDACTED]",
    ),
    # Windows user paths  C:\Users\john.doe\...
    (re.compile(r"[A-Z]:\\Users\\[\w.\- ]+"), r"C:\\Users\\[USER]"),
    # Linux home paths  /home/john/
    (re.compile(r"/home/[\w.\-]+"), "/home/[USER]"),
    # Long hex / base64 tokens (40+ alphanumeric chars)
    (re.compile(r"\b[A-Za-z0-9+/]{40,}\b"), "[DATA_REDACTED]"),
    # Email addresses
    (re.compile(r"\b[\w.\-+]+@[\w.\-]+\.\w+\b"), "[EMAIL_REDACTED]"),
]


def sanitize(text):
    """
    Scrub sensitive data from *text* using compiled regex rules.

    Safe to call on any string — returns the cleaned version.
    """
    if not text:
        return text
    for pattern, replacement in _SANITIZE_RULES:
        text = pattern.sub(replacement, text)
    return text


# ═══════════════════════════════════════════════════════════════════════════════
#  KB I/O
# ═══════════════════════════════════════════════════════════════════════════════

def _kb_file(kb_path):
    """Return the full path to the main kb.json."""
    return os.path.join(kb_path, "kb.json")


def load_kb(kb_path):
    """
    Load kb.json and return its contents as a list of dicts.

    Returns an empty list on any error (missing file, bad JSON, etc.).
    """
    path = _kb_file(kb_path)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, IOError, OSError):
        return []


def save_kb(kb_path, data):
    """Write *data* (list of dicts) to kb.json atomically."""
    path = _kb_file(kb_path)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        # Atomic rename (works on most OS; on Windows it replaces)
        if os.path.exists(path):
            os.replace(tmp, path)
        else:
            os.rename(tmp, path)
    except OSError:
        # Fallback: direct write
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════════════════
#  CONFLICT RESOLUTION  (OneDrive sync insurance)
# ═══════════════════════════════════════════════════════════════════════════════

def resolve_conflicts(kb_path):
    """
    Detect OneDrive conflict copies and merge them into the main kb.json.

    OneDrive typically creates files like:
        kb-DESKTOP-ABC123.json
        kb (1).json
        kb (John Doe's conflicted copy 2026-02-15).json

    Returns the number of new entries merged (0 if no conflicts found).
    """
    if not os.path.isdir(kb_path):
        return 0

    main_name = "kb.json"

    # Gather all JSON files that look like KB conflicts
    conflict_files = []
    for fname in os.listdir(kb_path):
        if not fname.endswith(".json"):
            continue
        if fname == main_name:
            continue
        # Match patterns: kb-*.json, kb (*.json, kb *.json, KB*.json
        lower = fname.lower()
        if lower.startswith("kb"):
            conflict_files.append(os.path.join(kb_path, fname))

    if not conflict_files:
        return 0

    # Load main KB
    main_data = load_kb(kb_path)

    # Build a dedup key set from existing entries
    existing_keys = set()
    for entry in main_data:
        key = _dedup_key(entry)
        existing_keys.add(key)

    merged = 0

    for cf_path in conflict_files:
        try:
            with open(cf_path, "r", encoding="utf-8") as fh:
                cf_data = json.load(fh)
            if not isinstance(cf_data, list):
                continue
            for entry in cf_data:
                key = _dedup_key(entry)
                if key not in existing_keys:
                    main_data.append(entry)
                    existing_keys.add(key)
                    merged += 1
            # Remove the conflict file after a successful read & merge
            os.remove(cf_path)
        except (json.JSONDecodeError, IOError, OSError):
            continue  # skip corrupt / locked files silently

    if merged > 0:
        save_kb(kb_path, main_data)

    return merged


def _dedup_key(entry):
    """Create a hashable key for deduplication (error + timestamp)."""
    return (
        entry.get("error", "").strip().lower(),
        entry.get("timestamp", ""),
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  FUZZY SEARCH
# ═══════════════════════════════════════════════════════════════════════════════

def fuzzy_search(query, kb_data, threshold=70):
    """
    Search *kb_data* for entries whose 'error' field matches *query*.

    Uses ``difflib.SequenceMatcher`` (stdlib, zero dependencies).

    Returns a list of ``(entry, score)`` tuples sorted by score desc.
    Only results ≥ *threshold* (0–100) are included.
    """
    if not kb_data or not query:
        return []

    query_lower = query.strip().lower()
    results = []

    for entry in kb_data:
        kb_error = entry.get("error", "").strip().lower()
        if not kb_error:
            continue

        # 1. SequenceMatcher ratio (0.0 – 1.0 → scaled to 0–100)
        score = SequenceMatcher(None, query_lower, kb_error).ratio() * 100

        # 2. Substring bonus — if one is fully contained in the other
        if kb_error in query_lower or query_lower in kb_error:
            score = max(score, 92.0)

        # 3. "Starts-with" bonus — common prefix match
        if query_lower.startswith(kb_error[:30]) or kb_error.startswith(query_lower[:30]):
            score = max(score, 85.0)

        if score >= threshold:
            results.append((entry, round(score, 1)))

    results.sort(key=lambda x: x[1], reverse=True)
    return results


# ═══════════════════════════════════════════════════════════════════════════════
#  ADD ENTRY
# ═══════════════════════════════════════════════════════════════════════════════

def add_entry(kb_path, error, solution, command, added_by):
    """
    Append a new solution to the KB.

    - Resolves conflicts first
    - Sanitizes the error signature
    - Prevents exact duplicates

    Returns ``(True, entry_dict)`` on success,
    or ``(False, reason_string)`` on failure.
    """
    if not error or not solution:
        return False, "Error and solution are required."

    resolve_conflicts(kb_path)
    data = load_kb(kb_path)

    sanitized_error = sanitize(error.strip())

    # Check for duplicates
    for existing in data:
        if existing.get("error", "").strip().lower() == sanitized_error.lower():
            return False, "This error already exists in the KB."

    entry = {
        "error": sanitized_error,
        "solution": solution.strip(),
        "command": command.strip() if command else "",
        "added_by": added_by,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    data.append(entry)
    save_kb(kb_path, data)
    return True, entry

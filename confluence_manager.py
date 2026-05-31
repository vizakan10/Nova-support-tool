#!/usr/bin/env python3
"""
Nova CLI — Confluence local index (sync + search).
"""

import base64
import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from config import CONFIG_DIR, NOVA_HTTP_USER_AGENT, load_secrets, save_secrets

CONFLUENCE_CONFIG_FILE = os.path.join(CONFIG_DIR, "confluence_config.json")
CONFLUENCE_INDEX_FILE = os.path.join(CONFIG_DIR, "confluence_index.json")

_PAGE_LIMIT = 50


def _ensure_dir():
    os.makedirs(CONFIG_DIR, exist_ok=True)


def load_confluence_config():
    """Load {domain, email, space_key} (no token)."""
    if not os.path.isfile(CONFLUENCE_CONFIG_FILE):
        return None
    try:
        with open(CONFLUENCE_CONFIG_FILE, "r", encoding="utf-8") as fh:
            cfg = json.load(fh)
        if not isinstance(cfg, dict):
            return None
        if cfg.get("domain") and cfg.get("email") and cfg.get("space_key"):
            return cfg
    except (json.JSONDecodeError, OSError):
        pass
    return None


def save_confluence_config(domain, email, space_key):
    """Persist Confluence connection settings (token stored separately)."""
    _ensure_dir()
    domain = (domain or "").strip().rstrip("/")
    if domain.startswith("https://"):
        domain = domain[8:]
    if domain.startswith("http://"):
        domain = domain[7:]
    cfg = {
        "domain": domain,
        "email": (email or "").strip(),
        "space_key": (space_key or "").strip(),
    }
    with open(CONFLUENCE_CONFIG_FILE, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2, ensure_ascii=False)


def save_confluence_token(token):
    """Store API token under secrets.json key 'confluence'."""
    secrets = load_secrets()
    secrets["confluence"] = (token or "").strip()
    save_secrets(secrets)


def get_confluence_token():
    return (load_secrets() or {}).get("confluence", "")


def confluence_index_exists():
    return os.path.isfile(CONFLUENCE_INDEX_FILE)


def _auth_header(email, token):
    raw = f"{email}:{token}".encode("utf-8")
    encoded = base64.b64encode(raw).decode("ascii")
    return f"Basic {encoded}"


def _normalize_domain(domain):
    domain = (domain or "").strip().rstrip("/")
    if domain.startswith("https://"):
        domain = domain[8:]
    if domain.startswith("http://"):
        domain = domain[7:]
    return domain


def _html_to_text(raw_html):
    if not raw_html:
        return ""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw_html, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _page_url(domain, page):
    links = page.get("_links") or {}
    webui = links.get("webui") or ""
    if webui:
        if webui.startswith("/"):
            return f"https://{domain}/wiki{webui}"
        return f"https://{domain}/wiki/{webui}"
    page_id = page.get("id", "")
    return f"https://{domain}/wiki/pages/{page_id}"


def _last_updated(page):
    version = page.get("version") or {}
    when = version.get("when") or page.get("history", {}).get("lastUpdated", {}).get("when")
    return when or ""


def _fetch_content_batch(domain, email, token, space_key, start):
    """Fetch one page of Confluence content results."""
    params = urllib.parse.urlencode({
        "spaceKey": space_key,
        "type": "page",
        "expand": "body.storage,version",
        "limit": _PAGE_LIMIT,
        "start": start,
    })
    url = f"https://{domain}/wiki/rest/api/content?{params}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", _auth_header(email, token))
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", NOVA_HTTP_USER_AGENT)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def sync_confluence(domain, email, token, space_key):
    """
    Fetch all pages from a Confluence space and save ~/.nova/confluence_index.json.
    Returns number of pages synced, or raises on API failure.
    """
    domain = _normalize_domain(domain)
    space_key = (space_key or "").strip()
    if not all([domain, email, token, space_key]):
        raise ValueError("domain, email, token, and space_key are required")

    all_pages = []
    start = 0
    while True:
        try:
            data = _fetch_content_batch(domain, email, token, space_key, start)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:400]
            raise RuntimeError(f"Confluence API error ({exc.code}): {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Confluence request failed: {exc}") from exc

        results = data.get("results") or []
        all_pages.extend(results)
        if len(results) < _PAGE_LIMIT:
            break
        start += len(results)

    total = len(all_pages)
    index = []
    for i, page in enumerate(all_pages, 1):
        title = (page.get("title") or "Untitled").strip()
        print(f"  Syncing page {i}/{total}: {title}...", flush=True)

        storage = (page.get("body") or {}).get("storage") or {}
        raw_html = storage.get("value") or ""
        text = _html_to_text(raw_html)
        index.append({
            "title": title,
            "url": _page_url(domain, page),
            "text": text,
            "last_updated": _last_updated(page),
        })

    _ensure_dir()
    with open(CONFLUENCE_INDEX_FILE, "w", encoding="utf-8") as fh:
        json.dump(index, fh, indent=2, ensure_ascii=False)

    return total


def _query_words(query):
    words = []
    for w in re.split(r"\s+", (query or "").lower()):
        w = w.strip(".,;:!?\"'()[]{}")
        if len(w) >= 2:
            words.append(w)
    return words


def _score_page(words, title, text):
    if not words:
        return 0
    title_l = (title or "").lower()
    text_l = (text or "").lower()
    score = 0
    for w in words:
        if w in title_l:
            score += 2
        if w in text_l:
            score += 1
    return score


def _excerpt(text, words, length=300):
    text = text or ""
    if not text:
        return ""
    text_l = text.lower()
    pos = -1
    for w in words:
        idx = text_l.find(w)
        if idx >= 0 and (pos < 0 or idx < pos):
            pos = idx
    if pos < 0:
        start = 0
        snippet = text[:length]
    else:
        half = length // 2
        start = max(0, pos - half)
        end = min(len(text), start + length)
        if end - start < length:
            start = max(0, end - length)
        snippet = text[start:end]
    snippet = re.sub(r"\s+", " ", snippet).strip()
    if start > 0:
        snippet = "..." + snippet
    if len(text) > start + length:
        snippet = snippet + "..."
    return snippet


def search_confluence(query, top_n=3):
    """
    Search local index by word overlap (title 2x, body 1x).
    Returns list of {title, url, excerpt, score} sorted by score.
    """
    if not confluence_index_exists():
        return []
    try:
        with open(CONFLUENCE_INDEX_FILE, "r", encoding="utf-8") as fh:
            pages = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(pages, list):
        return []

    words = _query_words(query)
    if not words:
        return []

    scored = []
    for page in pages:
        title = page.get("title") or ""
        text = page.get("text") or ""
        score = _score_page(words, title, text)
        if score > 0:
            scored.append({
                "title": title,
                "url": page.get("url") or "",
                "excerpt": _excerpt(text, words),
                "text": text,
                "score": score,
            })

    scored.sort(key=lambda x: (-x["score"], x["title"]))
    top = scored[:top_n]
    for item in top:
        item.pop("text", None)
        item.pop("score", None)
    return top


def format_confluence_context(results):
    """Build excerpt block for the AI prompt."""
    if not results:
        return ""
    parts = []
    for i, r in enumerate(results, 1):
        title = r.get("title") or "Untitled"
        url = r.get("url") or ""
        excerpt = r.get("excerpt") or ""
        parts.append(f"--- Document {i}: {title} ---\nURL: {url}\n{excerpt}")
    return "\n\n".join(parts)

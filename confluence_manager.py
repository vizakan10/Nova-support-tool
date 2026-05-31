#!/usr/bin/env python3
"""
Nova CLI — Confluence sync (local index) and live REST search (CQL).
Uses a Jira API token for auth; on IFS Atlassian Cloud it also works for Confluence.
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

DEFAULT_DOMAIN = "ifsdev.atlassian.net"
DEFAULT_SPACES = ["KAIROS", "NGA", "NEXUZ", "NEXT"]

CONFLUENCE_CONFIG_FILE = os.path.join(CONFIG_DIR, "confluence_config.json")
CONFLUENCE_INDEX_FILE = os.path.join(CONFIG_DIR, "confluence_index.json")

_PAGE_LIMIT = 50
_SEARCH_LIMIT_DEFAULT = 5


def _ensure_dir():
    os.makedirs(CONFIG_DIR, exist_ok=True)


def resolve_sync_space_keys(additional=None):
    """Default Kairos-related spaces plus optional extra keys (uppercased, deduped)."""
    keys = []
    seen = set()
    for sk in list(DEFAULT_SPACES) + list(additional or []):
        key = (sk or "").strip().upper()
        if key and key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def load_confluence_config():
    """Load {domain, email, space_keys} (no token)."""
    if not os.path.isfile(CONFLUENCE_CONFIG_FILE):
        return None
    try:
        with open(CONFLUENCE_CONFIG_FILE, "r", encoding="utf-8") as fh:
            cfg = json.load(fh)
        if not isinstance(cfg, dict) or not cfg.get("email"):
            return None
        domain = _normalize_domain(cfg.get("domain") or DEFAULT_DOMAIN)
        space_keys = cfg.get("space_keys")
        if not space_keys and cfg.get("space_key"):
            space_keys = [cfg["space_key"]]
        if not space_keys:
            space_keys = list(DEFAULT_SPACES)
        return {
            "domain": domain,
            "email": cfg["email"].strip(),
            "space_keys": resolve_sync_space_keys(space_keys),
        }
    except (json.JSONDecodeError, OSError):
        pass
    return None


def save_confluence_config(email, space_keys=None, domain=None):
    """Persist Confluence settings (token stored separately)."""
    _ensure_dir()
    cfg = {
        "domain": _normalize_domain(domain or DEFAULT_DOMAIN),
        "email": (email or "").strip(),
        "space_keys": resolve_sync_space_keys(space_keys or DEFAULT_SPACES),
    }
    with open(CONFLUENCE_CONFIG_FILE, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2, ensure_ascii=False)


def save_jira_token(token):
    """Store Jira API token (works for Confluence REST on IFS Atlassian Cloud)."""
    secrets = load_secrets()
    tok = (token or "").strip()
    secrets["jira"] = tok
    secrets["confluence"] = tok  # backward compatibility
    save_secrets(secrets)


def save_confluence_token(token):
    """Alias for save_jira_token."""
    save_jira_token(token)


def get_jira_token():
    secrets = load_secrets() or {}
    return (secrets.get("jira") or secrets.get("confluence") or "").strip()


def get_confluence_token():
    """Alias for get_jira_token."""
    return get_jira_token()


def confluence_credentials_ready():
    """True when domain, email, and API token are configured."""
    cfg = load_confluence_config()
    return bool(cfg and cfg.get("email") and get_jira_token())


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
    return domain or DEFAULT_DOMAIN


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


def _fetch_all_pages(domain, email, token, space_key):
    """Paginate and return all page objects for one space."""
    all_pages = []
    start = 0
    while True:
        try:
            data = _fetch_content_batch(domain, email, token, space_key, start)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:400]
            raise RuntimeError(
                f"Confluence API error for space {space_key} ({exc.code}): {body}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Confluence request failed for space {space_key}: {exc}") from exc

        results = data.get("results") or []
        all_pages.extend(results)
        if len(results) < _PAGE_LIMIT:
            break
        start += len(results)
    return all_pages


def _pages_to_index_entries(domain, all_pages, space_key):
    """Convert API pages to index dicts; print per-page progress."""
    total = len(all_pages)
    index = []
    for i, page in enumerate(all_pages, 1):
        title = (page.get("title") or "Untitled").strip()
        print(f"  [{space_key}] Syncing page {i}/{total}: {title}...", flush=True)

        storage = (page.get("body") or {}).get("storage") or {}
        raw_html = storage.get("value") or ""
        text = _html_to_text(raw_html)
        index.append({
            "title": title,
            "url": _page_url(domain, page),
            "text": text,
            "last_updated": _last_updated(page),
            "space_key": space_key,
        })
    return index


def sync_confluence_space(domain, email, token, space_key):
    """Fetch all pages from one space; return index entries (does not write file)."""
    domain = _normalize_domain(domain)
    space_key = (space_key or "").strip().upper()
    if not all([domain, email, token, space_key]):
        raise ValueError("domain, email, token, and space_key are required")
    pages = _fetch_all_pages(domain, email, token, space_key)
    return _pages_to_index_entries(domain, pages, space_key)


def sync_confluence_spaces(domain, email, token, space_keys):
    """
    Sync multiple Confluence spaces into ~/.nova/confluence_index.json.
    Returns total page count.
    """
    domain = _normalize_domain(domain)
    space_keys = resolve_sync_space_keys(space_keys)
    if not all([domain, email, token]) or not space_keys:
        raise ValueError("domain, email, token, and at least one space_key are required")

    merged = []
    for space_key in space_keys:
        print(f"\n  Space {space_key}:", flush=True)
        merged.extend(sync_confluence_space(domain, email, token, space_key))

    _ensure_dir()
    with open(CONFLUENCE_INDEX_FILE, "w", encoding="utf-8") as fh:
        json.dump(merged, fh, indent=2, ensure_ascii=False)
    return len(merged)


def sync_confluence(domain, email, token, space_key):
    """Backward-compatible single-space sync."""
    return sync_confluence_spaces(domain, email, token, [space_key])


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


def _build_text_cql(query):
    """CQL for full-text search, e.g. text ~ \"kairos deployment\"."""
    q = (query or "").strip()
    if not q:
        return None
    escaped = q.replace("\\", "\\\\").replace('"', '\\"')
    return f'text ~ "{escaped}"'


def _confluence_api_get(domain, email, token, path_query):
    """GET Confluence REST path under /wiki/rest/api/ (path_query includes leading resource)."""
    domain = _normalize_domain(domain)
    url = f"https://{domain}/wiki/rest/api/{path_query.lstrip('/')}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", _auth_header(email, token))
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", NOVA_HTTP_USER_AGENT)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"Confluence API error ({exc.code}): {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Confluence request failed: {exc}") from exc


def _hit_to_result(domain, hit, words):
    """Map one content/search result to {title, url, excerpt}."""
    title = (hit.get("title") or "Untitled").strip()
    url = _page_url(domain, hit)
    storage = (hit.get("body") or {}).get("storage") or {}
    text = _html_to_text(storage.get("value") or "")
    if text:
        excerpt = _excerpt(text, words) if words else (text[:300] + ("..." if len(text) > 300 else ""))
    else:
        excerpt = title
    return {"title": title, "url": url, "excerpt": excerpt}


def search_confluence_rest(domain, email, token, query, top_n=None):
    """
    Live search via GET /wiki/rest/api/content/search (CQL).
    Auth: Basic base64(email:jira_token).
    """
    domain = _normalize_domain(domain)
    cql = _build_text_cql(query)
    if not all([domain, email, token, cql]):
        return []
    limit = top_n if top_n is not None else _SEARCH_LIMIT_DEFAULT
    params = urllib.parse.urlencode({
        "cql": cql,
        "limit": limit,
        "expand": "body.storage",
    })
    data = _confluence_api_get(domain, email, token, f"content/search?{params}")
    results = data.get("results") or []
    words = _query_words(query)
    out = []
    for hit in results:
        if not isinstance(hit, dict):
            continue
        out.append(_hit_to_result(domain, hit, words))
    return out


def search_confluence_local(query, top_n=3):
    """Search local ~/.nova/confluence_index.json (used by nova csync offline copy)."""
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


def search_confluence(query, top_n=None, domain=None, email=None, token=None):
    """
    Search Confluence via REST API using saved or passed credentials.
    Returns list of {title, url, excerpt}.
    """
    cfg = load_confluence_config()
    if cfg:
        domain = domain or cfg.get("domain")
        email = email or cfg.get("email")
    token = token or get_jira_token()
    if not all([domain, email, token]):
        return []
    return search_confluence_rest(domain, email, token, query, top_n=top_n)


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

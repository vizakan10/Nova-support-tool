#!/usr/bin/env python3
"""
Nova CLI — NGA Confluence local RAG index + search for nova ask.
"""

import base64
import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone

from config import CONFIG_DIR, NOVA_HTTP_USER_AGENT, load_secrets, save_secrets

DEFAULT_DOMAIN = "ifsdev.atlassian.net"
DEFAULT_SPACES = ["KAIROS", "NGA", "NEXUZ", "NEXT"]
DEFAULT_PRIORITY_SPACES = ["NGA"]
DEFAULT_INDEX_SPACE = "NGA"

CONFLUENCE_CONFIG_FILE = os.path.join(CONFIG_DIR, "confluence_config.json")
CONFLUENCE_INDEX_FILE = os.path.join(CONFIG_DIR, "confluence_index.json")

_PAGE_LIMIT = 50
_SEARCH_LOCAL_TOP = 5
_SEARCH_AI_TOP = 3
MIN_STRONG_SCORE = 5
_MIN_STRONG_SCORE = MIN_STRONG_SCORE
SEARCH_LOCAL_TOP = _SEARCH_LOCAL_TOP
SEARCH_AI_TOP = _SEARCH_AI_TOP
_INDEX_STALE_DAYS = 7
_SUMMARY_LEN = 300
_KEYWORD_COUNT = 20
_AI_DOC_CHAR_LIMIT = 12000
_AI_DOC_CHAR_LIMIT_ASK = 5000
_AI_CONTEXT_TOTAL_CHARS = 14000
_SEARCH_POOL_TOP = 15

_STOPWORDS = frozenset({
    "the", "is", "and", "to", "a", "in", "of", "for", "with", "that", "this",
    "it", "are", "was", "be", "have", "has", "or", "but", "not", "on", "at",
    "by", "an", "as", "from", "into", "your", "you", "we", "our", "can", "will",
    "would", "should", "could", "been", "being", "their", "there", "when", "what",
    "which", "who", "how", "all", "any", "each", "other", "than", "then", "them",
    "these", "those", "such", "only", "also", "may", "might", "must", "shall",
    "do", "does", "did", "done", "am", "if", "so", "no", "yes", "up", "out",
    "about", "over", "after", "before", "between", "through", "during", "without",
    "within", "while", "where", "why", "because", "until", "unless", "upon",
    "via", "per", "etc", "eg", "ie", "want", "need", "like", "just", "get",
})


def _ensure_dir():
    os.makedirs(CONFIG_DIR, exist_ok=True)


def resolve_sync_space_keys(additional=None):
    keys = []
    seen = set()
    for sk in list(DEFAULT_SPACES) + list(additional or []):
        key = (sk or "").strip().upper()
        if key and key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def resolve_priority_spaces(keys=None):
    out = []
    seen = set()
    for sk in list(DEFAULT_PRIORITY_SPACES) + list(keys or []):
        key = (sk or "").strip().upper()
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out or list(DEFAULT_PRIORITY_SPACES)


def parse_priority_spaces_input(raw):
    if not (raw or "").strip():
        return list(DEFAULT_PRIORITY_SPACES)
    parts = [p.strip().upper() for p in raw.split(",") if p.strip()]
    return resolve_priority_spaces(parts) if parts else list(DEFAULT_PRIORITY_SPACES)


def load_confluence_config():
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
            "priority_spaces": resolve_priority_spaces(cfg.get("priority_spaces")),
        }
    except (json.JSONDecodeError, OSError):
        pass
    return None


def save_confluence_config(email, space_keys=None, domain=None, priority_spaces=None):
    _ensure_dir()
    existing = {}
    if os.path.isfile(CONFLUENCE_CONFIG_FILE):
        try:
            with open(CONFLUENCE_CONFIG_FILE, "r", encoding="utf-8") as fh:
                existing = json.load(fh)
        except (json.JSONDecodeError, OSError):
            existing = {}
    if priority_spaces is None:
        priority_spaces = existing.get("priority_spaces")
    cfg = {
        "domain": _normalize_domain(domain or existing.get("domain") or DEFAULT_DOMAIN),
        "email": (email or existing.get("email") or "").strip(),
        "space_keys": resolve_sync_space_keys(
            space_keys if space_keys is not None else existing.get("space_keys")
        ),
        "priority_spaces": resolve_priority_spaces(priority_spaces),
    }
    with open(CONFLUENCE_CONFIG_FILE, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2, ensure_ascii=False)


def save_jira_token(token):
    secrets = load_secrets()
    tok = (token or "").strip()
    secrets["jira"] = tok
    secrets["confluence"] = tok
    save_secrets(secrets)


def save_confluence_token(token):
    save_jira_token(token)


def get_jira_token():
    secrets = load_secrets() or {}
    return (secrets.get("jira") or secrets.get("confluence") or "").strip()


def get_confluence_token():
    return get_jira_token()


def confluence_credentials_ready():
    cfg = load_confluence_config()
    return bool(cfg and cfg.get("email") and get_jira_token())


def confluence_index_exists():
    data = load_index_data()
    return bool(data and data.get("pages"))


def ensure_local_index(interactive=True):
    """
    Return True if a usable local index exists.
    If credentials are saved but index is missing, optionally prompt to build it.
    """
    if confluence_index_exists():
        return True
    if not confluence_credentials_ready():
        return False
    if not interactive:
        return False
    cfg = load_confluence_config()
    token = get_jira_token()
    if not cfg or not token:
        return False
    try:
        ans = input(
            f"\n  {DEFAULT_INDEX_SPACE} index not built yet. "
            f"Scan all {DEFAULT_INDEX_SPACE} pages now? [Y/n]: "
        ).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    if ans not in ("", "y", "yes"):
        return False
    ok, err = verify_confluence_access(cfg["domain"], cfg["email"], token)
    if not ok:
        print(f"\n  ⚠ Cannot build index:\n  {err}\n")
        return False
    print(f"\n  ▶ Building local RAG index ({DEFAULT_INDEX_SPACE})...\n")
    try:
        build_confluence_index(
            cfg["domain"], cfg["email"], token, space_key=DEFAULT_INDEX_SPACE
        )
        return confluence_index_exists()
    except (ValueError, RuntimeError) as exc:
        print(f"  ⚠ Index build failed:\n  {exc}\n")
        return False


def _auth_header(email, token):
    """RFC 7617 Basic auth value for Confluence REST (email:api_token)."""
    raw = f"{email}:{token}".encode("utf-8")
    encoded = base64.b64encode(raw).decode("ascii")
    return f"Basic {encoded}"


def format_confluence_api_error(status_code, body, domain=None, email=None):
    """Turn Confluence HTTP errors into actionable messages."""
    domain = _normalize_domain(domain or DEFAULT_DOMAIN)
    body_l = (body or "").lower()
    if status_code == 403 and "not permitted to use confluence" in body_l:
        return (
            f"Confluence API denied for {email or 'this account'}.\n"
            f"  If you can open https://{domain}/wiki in the browser, usually:\n"
            f"  • Use a classic API token (no scopes) from https://id.atlassian.com/manage-profile/security/api-tokens\n"
            f"  • Email in  nova csetup  must match the account that created the token\n"
            f"  • Scoped tokens need different API URLs — Nova uses classic tokens on {domain}\n"
            f"  • Otherwise request Confluence product access / confluence-users group from IT"
        )
    if status_code == 401:
        return (
            "Confluence authentication failed (401).\n"
            "  • Check email matches the account that created the API token\n"
            "  • Create a new token at https://id.atlassian.com and run  nova csetup"
        )
    if status_code == 404:
        return f"Confluence API not found (404). Check domain is correct: {domain}"
    snippet = (body or "").strip()[:200]
    return f"Confluence API error ({status_code}): {snippet}"


def _confluence_get(domain, email, token, api_path, timeout=120):
    """GET {domain}/wiki/rest/api/{api_path} with basic auth."""
    domain = _normalize_domain(domain)
    path = api_path.lstrip("/")
    url = f"https://{domain}/wiki/rest/api/{path}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", _auth_header(email, token))
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", NOVA_HTTP_USER_AGENT)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            format_confluence_api_error(exc.code, body, domain=domain, email=email)
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Confluence request failed: {exc}") from exc


def verify_confluence_access(domain, email, token):
    """
    Quick check that this account can use Confluence REST (before a full NGA scan).
    Returns (True, None) or (False, error_message).
    """
    if not all([domain, email, token]):
        return False, "domain, email, and API token are required"
    try:
        _confluence_get(domain, email, token, "user/current", timeout=30)
        return True, None
    except RuntimeError as exc:
        return False, str(exc)


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
    return re.sub(r"\s+", " ", text).strip()


def _page_id(page):
    return str(page.get("id") or "").strip()


def _page_url(domain, page):
    links = page.get("_links") or {}
    webui = (links.get("webui") or "").strip()
    tinyui = (links.get("tinyui") or "").strip()
    base = (links.get("base") or "").strip().rstrip("/")
    if webui.startswith("http://") or webui.startswith("https://"):
        return webui
    if webui:
        if webui.startswith("/"):
            return f"https://{domain}/wiki{webui}"
        return f"https://{domain}/wiki/{webui}"
    if tinyui:
        if tinyui.startswith("/"):
            return f"https://{domain}/wiki{tinyui}"
        return f"https://{domain}/wiki/{tinyui}"
    if base and page.get("id"):
        return f"{base}/pages/viewpage.action?pageId={page.get('id')}"
    pid = page.get("id", "")
    if pid:
        return f"https://{domain}/wiki/pages/viewpage.action?pageId={pid}"
    return (page.get("url") or "").strip()


def _last_updated(page):
    version = page.get("version") or {}
    return version.get("when") or page.get("history", {}).get("lastUpdated", {}).get("when") or ""


def _hit_space_key(hit):
    space = hit.get("space")
    if isinstance(space, dict):
        key = space.get("key") or space.get("name") or ""
        if key:
            return str(key).strip().upper()
    expandable = hit.get("_expandable") or {}
    sp = expandable.get("space") or ""
    if "/space/" in sp:
        return sp.rstrip("/").split("/")[-1].upper()
    return (hit.get("space_key") or hit.get("space") or "").strip().upper()


def _fetch_content_batch(domain, email, token, space_key, start):
    params = urllib.parse.urlencode({
        "spaceKey": space_key,
        "type": "page",
        "expand": "body.storage,version,space",
        "limit": _PAGE_LIMIT,
        "start": start,
    })
    return _confluence_get(domain, email, token, f"content?{params}")


def _fetch_all_pages(domain, email, token, space_key):
    all_pages = []
    start = 0
    while True:
        data = _fetch_content_batch(domain, email, token, space_key, start)
        results = data.get("results") or []
        all_pages.extend(results)
        if len(results) < _PAGE_LIMIT:
            break
        start += len(results)
    return all_pages


def _tokenize_for_keywords(text):
    words = []
    for w in re.findall(r"[a-z0-9][a-z0-9_-]{1,}", (text or "").lower()):
        if w not in _STOPWORDS and len(w) >= 3:
            words.append(w)
    return words


def extract_keywords(full_text, count=_KEYWORD_COUNT):
    """Top keywords by frequency (stopwords removed)."""
    tokens = _tokenize_for_keywords(full_text)
    if not tokens:
        return []
    freq = Counter(tokens)
    return [w for w, _ in freq.most_common(count)]


def split_query_words(query):
    words = []
    for w in re.split(r"\s+", (query or "").lower()):
        w = w.strip(".,;:!?\"'()[]{}")
        if len(w) >= 2 and w not in _STOPWORDS:
            words.append(w)
    return words


def _word_matches_text(word, text_l):
    """Match query token to title/body (debug/debugger, vscode)."""
    if word in text_l:
        return True
    if word.startswith("debug") and "debug" in text_l:
        return True
    if word == "vscode" and ("vscode" in text_l or "vs code" in text_l):
        return True
    return False


def _page_to_rag_entry(domain, page, space_key):
    title = (page.get("title") or "Untitled").strip()
    storage = (page.get("body") or {}).get("storage") or {}
    full_text = _html_to_text(storage.get("value") or "")
    sk = _hit_space_key(page) or space_key
    summary = full_text[:_SUMMARY_LEN] + ("..." if len(full_text) > _SUMMARY_LEN else "") if full_text else title
    return {
        "id": _page_id(page),
        "title": title,
        "url": _page_url(domain, page),
        "space": sk,
        "space_key": sk,
        "full_text": full_text,
        "keywords": extract_keywords(full_text),
        "summary": summary,
        "last_updated": _last_updated(page),
    }


def _build_pages_from_api(domain, email, token, space_key, progress=True):
    space_key = (space_key or DEFAULT_INDEX_SPACE).strip().upper()
    raw_pages = _fetch_all_pages(domain, email, token, space_key)
    total = len(raw_pages)
    entries = []
    for i, page in enumerate(raw_pages, 1):
        entry = _page_to_rag_entry(domain, page, space_key)
        if progress:
            print(f"  Scanning page {i}/{total}: {entry['title']}...", flush=True)
        entries.append(entry)
    return entries


def load_index_data():
    if not os.path.isfile(CONFLUENCE_INDEX_FILE):
        return None
    try:
        with open(CONFLUENCE_INDEX_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None
    if isinstance(data, list):
        return {
            "last_sync": None,
            "space_key": DEFAULT_INDEX_SPACE,
            "domain": DEFAULT_DOMAIN,
            "page_count": len(data),
            "pages": data,
        }
    if isinstance(data, dict) and data.get("pages"):
        return data
    return None


def save_index_data(domain, space_key, pages):
    _ensure_dir()
    payload = {
        "last_sync": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "space_key": (space_key or DEFAULT_INDEX_SPACE).strip().upper(),
        "domain": _normalize_domain(domain),
        "page_count": len(pages),
        "pages": pages,
    }
    with open(CONFLUENCE_INDEX_FILE, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    return payload


def build_confluence_index(domain, email, token, space_key=DEFAULT_INDEX_SPACE):
    """
    Full RAG scan of one Confluence space → ~/.nova/confluence_index.json
    """
    domain = _normalize_domain(domain)
    space_key = (space_key or DEFAULT_INDEX_SPACE).strip().upper()
    if not all([domain, email, token, space_key]):
        raise ValueError("domain, email, token, and space_key are required")

    ok, err = verify_confluence_access(domain, email, token)
    if not ok:
        raise RuntimeError(err)

    pages = _build_pages_from_api(domain, email, token, space_key, progress=True)
    save_index_data(domain, space_key, pages)
    print(f"  ✓ Indexed {len(pages)} pages from {space_key} space")
    return len(pages)


def refresh_confluence_index(domain, email, token, space_key=DEFAULT_INDEX_SPACE):
    """
    Rescan space and report new/updated pages vs previous index.
    Returns {new, updated, total, pages}.
    """
    domain = _normalize_domain(domain)
    space_key = (space_key or DEFAULT_INDEX_SPACE).strip().upper()
    old_data = load_index_data() or {}
    old_by_id = {p.get("id"): p for p in (old_data.get("pages") or []) if p.get("id")}

    print(f"  ↻ Refreshing {space_key} index...")
    new_pages = _build_pages_from_api(domain, email, token, space_key, progress=True)

    new_count = 0
    updated_count = 0
    for page in new_pages:
        pid = page.get("id")
        old = old_by_id.get(pid)
        if not old:
            new_count += 1
        elif (old.get("last_updated") or "") != (page.get("last_updated") or ""):
            updated_count += 1

    save_index_data(domain, space_key, new_pages)
    print(f"  + {new_count} new page{'s' if new_count != 1 else ''} found")
    print(f"  ~ {updated_count} page{'s' if updated_count != 1 else ''} updated")
    print(f"  ✓ Index updated — {len(new_pages)} pages total")
    return {
        "new": new_count,
        "updated": updated_count,
        "total": len(new_pages),
        "pages": new_pages,
    }


def index_stale_message():
    """Return warning string if index older than 7 days, else None."""
    data = load_index_data()
    if not data or not data.get("last_sync"):
        return None
    try:
        synced = datetime.fromisoformat(data["last_sync"].replace("Z", "+00:00"))
    except ValueError:
        return None
    age_days = (datetime.now(timezone.utc) - synced).days
    if age_days > _INDEX_STALE_DAYS:
        return (
            f"⚠ Confluence index is {age_days} days old. "
            f"Run: nova csync -r to refresh"
        )
    return None


def _score_rag_page(page, query_words, phrase):
    title_l = (page.get("title") or "").lower()
    text_l = (
        page.get("full_text") or page.get("text") or page.get("summary") or ""
    ).lower()
    keywords = [k.lower() for k in (page.get("keywords") or [])]
    if not keywords and text_l:
        keywords = _tokenize_for_keywords(text_l[:2000])
    score = 0
    title_hits = 0
    for w in query_words:
        if _word_matches_text(w, title_l):
            score += 5
            title_hits += 1
        if any(_word_matches_text(w, k) for k in keywords):
            score += 3
        if _word_matches_text(w, text_l):
            score += 1
    if title_hits >= 2:
        score += 10
    if title_l.startswith("wip:") or title_l.startswith("[wip]"):
        score -= 8
    if any(w in query_words for w in ("debug", "debugger", "debugging")):
        if "debug" in title_l:
            score += 12
    if phrase and len(phrase) >= 4:
        if phrase in title_l:
            score += 10
        if phrase in text_l:
            score += 5
    return score


def search_local_index(query, top_n=_SEARCH_LOCAL_TOP):
    """
    Search local RAG index. Returns top N dicts with score, title, url, summary,
    id, space, full_text (for AI).
    """
    data = load_index_data()
    if not data:
        return []
    pages = data.get("pages") or []
    if not pages:
        return []

    query_words = split_query_words(query)
    phrase = (query or "").strip().lower()
    if not query_words and not phrase:
        return []

    scored = []
    for page in pages:
        score = _score_rag_page(page, query_words, phrase)
        if score > 0:
            item = dict(page)
            item["score"] = score
            item["space_key"] = page.get("space") or page.get("space_key") or ""
            scored.append(item)

    scored.sort(key=lambda x: (-x["score"], x.get("title") or ""))
    return scored[:top_n]


def ai_rank_score(page, query):
    """Relevance score for ordering UI and AI context (higher = better fit)."""
    query_words = split_query_words(query)
    base = page.get("score", 0)
    title_l = (page.get("title") or "").lower()
    if title_l.startswith("wip:") or title_l.startswith("[wip]"):
        base -= 8
    title_hits = sum(1 for w in query_words if _word_matches_text(w, title_l))
    extra = title_hits * 6
    if any(w in query_words for w in ("debug", "debugger", "debugging")) and "debug" in title_l:
        extra += 10
    return base + extra


def sort_ranked_for_query(ranked_pages, query):
    return sorted(
        ranked_pages,
        key=lambda p: (-ai_rank_score(p, query), p.get("title") or ""),
    )


def select_pages_for_ai_context(ranked_pages, query, top_n=_SEARCH_AI_TOP):
    """Pick best pages for AI using query + score (title relevance beats tie scores)."""
    if not ranked_pages:
        return []
    ordered = sort_ranked_for_query(ranked_pages, query)
    best = ai_rank_score(ordered[0], query)
    second = ai_rank_score(ordered[1], query) if len(ordered) > 1 else 0
    if best - second >= 10:
        use_n = 1
    elif best - second >= 5:
        use_n = min(2, top_n)
    else:
        use_n = top_n
    return pages_for_ai_context(
        ordered,
        top_n=use_n,
        char_limit_per_page=_AI_DOC_CHAR_LIMIT_ASK,
        total_char_limit=_AI_CONTEXT_TOTAL_CHARS,
    )


def pages_for_ai_context(
    ranked_pages,
    top_n=_SEARCH_AI_TOP,
    *,
    char_limit_per_page=_AI_DOC_CHAR_LIMIT,
    total_char_limit=None,
):
    """Top pages using stored full_text (no API)."""
    out = []
    total = 0
    for page in ranked_pages[:top_n]:
        full_text = (
            page.get("full_text") or page.get("text") or page.get("summary") or ""
        )
        limit = char_limit_per_page
        if total_char_limit is not None:
            remaining = total_char_limit - total
            if remaining <= 0:
                break
            limit = min(limit, remaining)
        text = full_text[:limit] if len(full_text) > limit else full_text
        total += len(text)
        out.append({
            "id": page.get("id"),
            "title": page.get("title") or "Untitled",
            "url": page.get("url") or "",
            "space_key": page.get("space") or page.get("space_key") or "",
            "excerpt": text,
            "score": page.get("score", 0),
        })
    return out


def format_confluence_context(results, *, use_full_text=False):
    if not results:
        return ""
    parts = []
    for i, r in enumerate(results, 1):
        title = r.get("title") or "Untitled"
        sk = r.get("space_key") or r.get("space") or ""
        label = f"[{sk}] {title}" if sk else title
        url = r.get("url") or ""
        body = r.get("excerpt") or r.get("summary") or ""
        if use_full_text:
            body = r.get("excerpt") or r.get("full_text") or r.get("summary") or ""
        parts.append(f"--- Document {i}: {label} ---\nURL: {url}\n{body}")
    return "\n\n".join(parts)


def get_index_page_by_id(page_id):
    data = load_index_data()
    if not data:
        return None
    for page in data.get("pages") or []:
        if str(page.get("id")) == str(page_id):
            return page
    return None


# ── Legacy / compat ───────────────────────────────────────────────────────────

def sync_priority_spaces_index(domain, email, token, priority_spaces=None):
    space = (resolve_priority_spaces(priority_spaces) or [DEFAULT_INDEX_SPACE])[0]
    return build_confluence_index(domain, email, token, space_key=space)


def sync_confluence_spaces(domain, email, token, space_keys):
    """Full multi-space sync (legacy); prefer build_confluence_index for NGA RAG."""
    domain = _normalize_domain(domain)
    space_keys = resolve_sync_space_keys(space_keys)
    merged = []
    for space_key in space_keys:
        print(f"\n  Space {space_key}:", flush=True)
        merged.extend(_build_pages_from_api(domain, email, token, space_key, progress=True))
    save_index_data(domain, space_keys[0] if space_keys else DEFAULT_INDEX_SPACE, merged)
    return len(merged)


def sync_confluence_space(domain, email, token, space_key):
    return build_confluence_index(domain, email, token, space_key=space_key)


def sync_confluence(domain, email, token, space_key):
    return build_confluence_index(domain, email, token, space_key=space_key)


def search_confluence(query, top_n=None, domain=None, email=None, token=None):
    """Primary search: local RAG index (no API)."""
    _ = domain, email, token
    return search_local_index(query, top_n=top_n or _SEARCH_LOCAL_TOP)


def search_confluence_local(query, top_n=3):
    return search_local_index(query, top_n=top_n)


def sample_index_entry():
    """Example entry shape for documentation."""
    return {
        "id": "3419865246",
        "title": "NGA / Kairos Planning Page - Y26Q4",
        "url": "https://ifsdev.atlassian.net/wiki/spaces/AFPM/pages/3419865246/NGA+Kairos+Planning+Page",
        "space": "NGA",
        "full_text": "This page describes the Kairos deployment process for the NGA team...",
        "keywords": ["kairos", "deployment", "nga", "staging", "pipeline", "helm"],
        "summary": "This page describes the Kairos deployment process for the NGA team. Prerequisites include...",
        "last_updated": "2026-05-15T10:30:00.000Z",
    }

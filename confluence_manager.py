#!/usr/bin/env python3
"""
Nova CLI — Confluence sync (local index) and smart search for nova ask.
Uses a Jira API token for auth; on IFS Cloud it also works for Confluence.
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
DEFAULT_PRIORITY_SPACES = ["NGA"]

CONFLUENCE_CONFIG_FILE = os.path.join(CONFIG_DIR, "confluence_config.json")
CONFLUENCE_INDEX_FILE = os.path.join(CONFIG_DIR, "confluence_index.json")

_PAGE_LIMIT = 50
_SEARCH_TOP_N = 3
_STAGE1_MIN_RESULTS = 3
_SUMMARY_MAX_LEN = 500


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


def resolve_priority_spaces(keys=None):
    """Priority search spaces; NGA first by default."""
    out = []
    seen = set()
    for sk in list(DEFAULT_PRIORITY_SPACES) + list(keys or []):
        key = (sk or "").strip().upper()
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out or list(DEFAULT_PRIORITY_SPACES)


def parse_priority_spaces_input(raw):
    """Parse comma-separated space keys; empty input → default NGA."""
    if not (raw or "").strip():
        return list(DEFAULT_PRIORITY_SPACES)
    parts = [p.strip().upper() for p in raw.split(",") if p.strip()]
    return resolve_priority_spaces(parts) if parts else list(DEFAULT_PRIORITY_SPACES)


def load_confluence_config():
    """Load {domain, email, space_keys, priority_spaces} (no token)."""
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
    """Persist Confluence settings (token stored separately)."""
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
    """Store Jira API token (works for Confluence REST on IFS Atlassian Cloud)."""
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


def _page_id(page):
    return str(page.get("id") or "").strip()


def _page_url(domain, page):
    """Build a browser URL from Confluence _links (page, folder, database, etc.)."""
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

    page_id = page.get("id", "")
    if page_id:
        return f"https://{domain}/wiki/pages/viewpage.action?pageId={page_id}"
    return (page.get("url") or "").strip()


def _last_updated(page):
    version = page.get("version") or {}
    when = version.get("when") or page.get("history", {}).get("lastUpdated", {}).get("when")
    return when or ""


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
    return (hit.get("space_key") or "").strip().upper()


def _page_summary(page, max_len=_SUMMARY_MAX_LEN):
    storage = (page.get("body") or {}).get("storage") or {}
    text = _html_to_text(storage.get("value") or "")
    if text:
        if len(text) > max_len:
            return text[:max_len] + "..."
        return text
    return (page.get("title") or "Untitled").strip()


def _fetch_content_batch(domain, email, token, space_key, start):
    params = urllib.parse.urlencode({
        "spaceKey": space_key,
        "type": "page",
        "expand": "body.storage,version,space",
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


def _pages_to_index_entries(domain, all_pages, space_key, *, light=False):
    """Full index (text) or light index (id, title, url, summary) for fast local search."""
    total = len(all_pages)
    index = []
    for i, page in enumerate(all_pages, 1):
        title = (page.get("title") or "Untitled").strip()
        sk = _hit_space_key(page) or space_key
        print(f"  [{sk}] Indexing page {i}/{total}: {title}...", flush=True)

        entry = {
            "id": _page_id(page),
            "title": title,
            "url": _page_url(domain, page),
            "space_key": sk,
            "last_updated": _last_updated(page),
        }
        if light:
            entry["summary"] = _page_summary(page)
        else:
            storage = (page.get("body") or {}).get("storage") or {}
            entry["text"] = _html_to_text(storage.get("value") or "")
            entry["summary"] = entry["text"][:_SUMMARY_MAX_LEN] if entry["text"] else title
        index.append(entry)
    return index


def sync_priority_spaces_index(domain, email, token, priority_spaces=None):
    """
    Light scan of priority spaces → ~/.nova/confluence_index.json
    (id, title, url, summary) for fast local page picking in nova ask.
    """
    domain = _normalize_domain(domain)
    priority_spaces = resolve_priority_spaces(priority_spaces)
    if not all([domain, email, token]) or not priority_spaces:
        raise ValueError("domain, email, token, and priority_spaces are required")

    merged = []
    for space_key in priority_spaces:
        print(f"\n  Priority space {space_key}:", flush=True)
        pages = _fetch_all_pages(domain, email, token, space_key)
        merged.extend(_pages_to_index_entries(domain, pages, space_key, light=True))

    _ensure_dir()
    with open(CONFLUENCE_INDEX_FILE, "w", encoding="utf-8") as fh:
        json.dump(merged, fh, indent=2, ensure_ascii=False)
    return len(merged)


def sync_confluence_space(domain, email, token, space_key):
    domain = _normalize_domain(domain)
    space_key = (space_key or "").strip().upper()
    if not all([domain, email, token, space_key]):
        raise ValueError("domain, email, token, and space_key are required")
    pages = _fetch_all_pages(domain, email, token, space_key)
    return _pages_to_index_entries(domain, pages, space_key, light=False)


def sync_confluence_spaces(domain, email, token, space_keys):
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
    return sync_confluence_spaces(domain, email, token, [space_key])


def _query_words(query):
    words = []
    for w in re.split(r"\s+", (query or "").lower()):
        w = w.strip(".,;:!?\"'()[]{}")
        if len(w) >= 2:
            words.append(w)
    return words


def _rank_hit(hit, words, priority_spaces):
    """Title +3/word, priority space +5, URL +2/word."""
    if not words:
        return 0
    title_l = (hit.get("title") or "").lower()
    url_l = (hit.get("url") or "").lower()
    sk = (hit.get("space_key") or "").strip().upper()
    score = 0
    for w in words:
        if w in title_l:
            score += 3
        if w in url_l:
            score += 2
    if sk in priority_spaces:
        score += 5
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


def _build_text_cql(query, space_keys=None):
    q = (query or "").strip()
    if not q:
        return None
    escaped = q.replace("\\", "\\\\").replace('"', '\\"')
    cql = f'text ~ "{escaped}"'
    if space_keys:
        keys = ", ".join(f'"{k}"' for k in resolve_priority_spaces(space_keys))
        cql += f" AND space in ({keys})"
    cql += " ORDER BY lastModified DESC"
    return cql


def _confluence_api_get(domain, email, token, path_query):
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


def fetch_content_by_id(domain, email, token, page_id):
    """Fetch one page with full body for AI context."""
    if not page_id:
        return None
    params = urllib.parse.urlencode({"expand": "body.storage,version,space"})
    return _confluence_api_get(domain, email, token, f"content/{page_id}?{params}")


def _search_cql(domain, email, token, query, space_keys=None, limit=10):
    cql = _build_text_cql(query, space_keys=space_keys)
    if not cql:
        return []
    params = urllib.parse.urlencode({
        "cql": cql,
        "limit": limit,
        "expand": "body.storage,space",
    })
    data = _confluence_api_get(domain, email, token, f"content/search?{params}")
    return data.get("results") or []


def _hit_to_result(domain, hit, words, priority_spaces):
    title = (hit.get("title") or "Untitled").strip()
    url = _page_url(domain, hit)
    sk = _hit_space_key(hit)
    storage = (hit.get("body") or {}).get("storage") or {}
    text = _html_to_text(storage.get("value") or "")
    if text:
        excerpt = _excerpt(text, words) if words else (text[:300] + ("..." if len(text) > 300 else ""))
    else:
        excerpt = (hit.get("summary") or title)
    return {
        "id": _page_id(hit),
        "title": title,
        "url": url,
        "excerpt": excerpt,
        "space_key": sk,
        "score": _rank_hit(
            {"title": title, "url": url, "space_key": sk},
            words,
            priority_spaces,
        ),
    }


def _search_local_index_ranked(query, priority_spaces, top_n=10):
    """Keyword search on local index; prefer priority spaces."""
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

    priority_set = set(resolve_priority_spaces(priority_spaces))
    scored = []
    for page in pages:
        sk = (page.get("space_key") or "").upper()
        if priority_set and sk and sk not in priority_set:
            continue
        body = page.get("summary") or page.get("text") or ""
        hit = {
            "id": page.get("id") or "",
            "title": page.get("title") or "",
            "url": page.get("url") or "",
            "space_key": sk,
            "summary": body,
        }
        score = _rank_hit(hit, words, priority_spaces)
        if score > 0:
            hit["score"] = score
            scored.append(hit)

    scored.sort(key=lambda x: (-x["score"], x.get("title") or ""))
    return scored[:top_n]


def _hydrate_from_local_picks(domain, email, token, picks, query, priority_spaces):
    """Fetch full content for top local index matches."""
    words = _query_words(query)
    out = []
    for pick in picks:
        pid = pick.get("id")
        if pid:
            try:
                page = fetch_content_by_id(domain, email, token, pid)
            except RuntimeError:
                page = None
            if page:
                item = _hit_to_result(domain, page, words, priority_spaces)
                item["score"] = max(item.get("score", 0), pick.get("score", 0))
                if not (item.get("url") or "").strip() and pick.get("url"):
                    item["url"] = pick["url"]
                out.append(item)
                continue
        item = {
            "id": pid,
            "title": pick.get("title") or "Untitled",
            "url": pick.get("url") or _page_url(domain, {"id": pid}),
            "excerpt": _excerpt(pick.get("summary") or "", words),
            "space_key": pick.get("space_key") or "",
            "score": pick.get("score", 0),
        }
        out.append(item)
    return _finalize_results(out, priority_spaces, words, domain=domain)


def _api_hits_to_ranked(domain, hits, query, priority_spaces):
    words = _query_words(query)
    out = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        item = _hit_to_result(domain, hit, words, priority_spaces)
        out.append(item)
    out.sort(key=lambda x: (-x.get("score", 0), x.get("title") or ""))
    return out


def _dedupe_by_id(hits):
    seen = set()
    out = []
    for h in hits:
        hid = _page_id(h) if isinstance(h, dict) else ""
        if hid and hid in seen:
            continue
        if hid:
            seen.add(hid)
        out.append(h)
    return out


def _ensure_result_urls(domain, items):
    """Fill missing URLs from page id so nova ask can print links."""
    domain = _normalize_domain(domain)
    for item in items:
        if (item.get("url") or "").strip():
            continue
        pid = item.get("id")
        if pid:
            item["url"] = f"https://{domain}/wiki/pages/viewpage.action?pageId={pid}"
    return items


def _finalize_results(items, priority_spaces, words, domain=None):
    """Re-rank, drop internal scores, return top N."""
    for item in items:
        if "score" not in item or not item["score"]:
            item["score"] = _rank_hit(item, words, priority_spaces)
    items.sort(key=lambda x: (-x.get("score", 0), x.get("title") or ""))
    top = items[:_SEARCH_TOP_N]
    for item in top:
        item.pop("score", None)
    if domain:
        _ensure_result_urls(domain, top)
    return top


def search_confluence_rest(domain, email, token, query, top_n=None, priority_spaces=None):
    """Two-stage CQL search with ranking (legacy direct REST entry)."""
    priority_spaces = resolve_priority_spaces(priority_spaces)
    top_n = top_n if top_n is not None else _SEARCH_TOP_N
    words = _query_words(query)

    stage1 = _search_cql(domain, email, token, query, space_keys=priority_spaces, limit=10)
    if len(stage1) >= _STAGE1_MIN_RESULTS:
        ranked = _api_hits_to_ranked(domain, stage1, query, priority_spaces)
        return _finalize_results(ranked, priority_spaces, words, domain=domain)[:top_n]

    stage2 = _search_cql(domain, email, token, query, space_keys=None, limit=10)
    combined = _dedupe_by_id(stage1 + stage2)
    ranked = _api_hits_to_ranked(domain, combined, query, priority_spaces)
    return _finalize_results(ranked, priority_spaces, words, domain=domain)[:top_n]


def search_confluence_local(query, top_n=3):
    """Search local index only (no API hydration)."""
    cfg = load_confluence_config()
    priority = cfg.get("priority_spaces") if cfg else DEFAULT_PRIORITY_SPACES
    ranked = _search_local_index_ranked(query, priority, top_n=top_n or _SEARCH_TOP_N)
    words = _query_words(query)
    dom = (cfg or {}).get("domain") or DEFAULT_DOMAIN
    return _finalize_results(ranked, priority, words, domain=dom)


def search_confluence(query, top_n=None, domain=None, email=None, token=None):
    """
    Smart search for nova ask:
      1) Local priority-space index → top page IDs (instant)
      2) Fetch full content for those pages via API
      3) Else two-stage CQL (priority spaces, then all spaces) + rank → top 3
    """
    cfg = load_confluence_config()
    if cfg:
        domain = domain or cfg.get("domain")
        email = email or cfg.get("email")
        priority_spaces = cfg.get("priority_spaces") or DEFAULT_PRIORITY_SPACES
    else:
        priority_spaces = list(DEFAULT_PRIORITY_SPACES)
    token = token or get_jira_token()
    if not all([domain, email, token]):
        return []

    top_n = top_n if top_n is not None else _SEARCH_TOP_N
    words = _query_words(query)

    local_ranked = _search_local_index_ranked(query, priority_spaces, top_n=10)
    if local_ranked and local_ranked[0].get("score", 0) > 0:
        hydrated = _hydrate_from_local_picks(
            domain, email, token, local_ranked[:top_n], query, priority_spaces
        )
        if hydrated:
            _ensure_result_urls(domain, hydrated)
            return hydrated

    stage1 = _search_cql(domain, email, token, query, space_keys=priority_spaces, limit=10)
    if len(stage1) >= _STAGE1_MIN_RESULTS:
        ranked = _api_hits_to_ranked(domain, stage1, query, priority_spaces)
        return _finalize_results(ranked, priority_spaces, words, domain=domain)[:top_n]

    stage2 = _search_cql(domain, email, token, query, space_keys=None, limit=10)
    combined = _dedupe_by_id(stage1 + stage2)
    ranked = _api_hits_to_ranked(domain, combined, query, priority_spaces)
    return _finalize_results(ranked, priority_spaces, words, domain=domain)[:top_n]


def format_confluence_context(results):
    if not results:
        return ""
    parts = []
    for i, r in enumerate(results, 1):
        title = r.get("title") or "Untitled"
        sk = r.get("space_key") or ""
        label = f"[{sk}] {title}" if sk else title
        url = r.get("url") or ""
        excerpt = r.get("excerpt") or ""
        parts.append(f"--- Document {i}: {label} ---\nURL: {url}\n{excerpt}")
    return "\n\n".join(parts)

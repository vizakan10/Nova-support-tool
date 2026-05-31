# Nova — Architecture

## NGA local RAG index

File: `~/.nova/confluence_index.json`

```json
{
  "last_sync": "2026-05-31T12:00:00Z",
  "space_key": "NGA",
  "domain": "ifsdev.atlassian.net",
  "page_count": 87,
  "pages": [ { "id", "title", "url", "space", "full_text", "keywords", "summary", "last_updated" } ]
}
```

Built by `build_confluence_index()` / refreshed by `nova csync -r`.

## `nova up` flow

1. Capture last terminal error (hooks)
2. **KB** — fuzzy search; strong match → show fix and stop
3. **Confluence** — local NGA index; strong match → AI with page text
4. **AI** — error-only fallback; optional save to KB

## `nova ask` flow

1. Warn if `last_sync` > 7 days old
2. **Confluence** — `search_local_index(query)`; top 5; weak → user pick
3. **KB** — fuzzy search; ≥70% match → show KB solution and stop
4. **AI** — Confluence context, KB hints, or general knowledge

## Scoring (local)

| Signal | Points |
|--------|--------|
| Query word in title | +5 each |
| Query word in keywords | +3 each |
| Query word in full_text | +1 each |
| Exact phrase in title | +10 |
| Exact phrase in full_text | +5 |

## Commands

| Command | Action |
|---------|--------|
| `nova csetup` | Credentials + optional NGA full scan |
| `nova csync -r` | Rescan NGA, show +new / ~updated |
| `nova ask` | Confluence → KB → AI |
| `nova up` | KB → Confluence → AI |

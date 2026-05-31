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

## `nova ask` flow

1. Warn if `last_sync` > 7 days old
2. `search_local_index(query)` — instant, no API
3. Show top 5 with scores
4. If top score < 5 → user picks page 1–5 or skips
5. Else top 3 `full_text` from index → AI (no API)
6. Stream answer citing pages

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
| `nova ask` | Local RAG + AI |

# Nova — Architecture

## Confluence and Jira authentication

Nova talks to **Atlassian Cloud** at `ifsdev.atlassian.net` (configurable via `nova csetup`).

On this instance, a **Jira API token** works for Confluence REST as well.

| File | Contents |
|------|----------|
| `confluence_config.json` | `domain`, `email`, `space_keys`, `priority_spaces` |
| `secrets.json` | `jira` API token |
| `confluence_index.json` | Light index: `id`, `title`, `url`, `summary`, `space_key` |

Default **priority space**: `NGA` (Next Generation Architecture).

## `nova csetup`

1. Atlassian domain (default `ifsdev.atlassian.net`)
2. Email
3. Jira/Atlassian API token
4. **Priority spaces** `[NGA]` — searched first (comma-separated, e.g. `NGA,KAIROS`)
5. **Scan priority spaces now?** `[Y/n]` — builds `confluence_index.json` (titles, IDs, summaries)

## `nova ask` — search flow

```
Question
  → Local index keyword search (priority spaces only) → top 3 page IDs
  → GET /wiki/rest/api/content/{id}?expand=body.storage  (full content for AI)
  → If no/local miss:
       Stage 1 CQL: text ~ "query" AND space in ("NGA",...) ORDER BY lastModified DESC
       If ≥3 hits → use those
       Else Stage 2: text ~ "query" across all spaces
  → Rank: title +3/word, priority space +5, URL +2/word → top 3
  → AI prompt with excerpts → streamed answer
```

Display: `• [NGA] Kairos Deployment Process`

## `nova csync`

Full download of sync spaces (`KAIROS`, `NGA`, `NEXUZ`, `NEXT`) with page body text. Optional; `nova ask` works with light index + live API.

## Module map

| Module | Role |
|--------|------|
| `nova_cli.py` | CLI: `csetup`, `csync`, `ask` |
| `confluence_manager.py` | Index scan, two-stage CQL, ranking, hydration |

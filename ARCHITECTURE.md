# Nova — Architecture

## Confluence and Jira authentication

Nova talks to **Atlassian Cloud** at `ifsdev.atlassian.net` (configurable via `nova csetup`).

On this instance, Atlassian accepts a **single Jira API token** for both:

- Jira REST (`/rest/api/3/...`)
- Confluence REST (`/wiki/rest/api/...`)

There is **no Rovo REST search API** on the site URL. `nova ask` does not call Rovo; it uses the **Confluence Content Search API**.

Credentials are stored under `~/.nova/`:

| File | Contents |
|------|----------|
| `confluence_config.json` | `domain`, `email`, `space_keys` (no token) |
| `secrets.json` | `jira` API token (legacy key `confluence` still read) |

## `nova csetup` — configure credentials

Interactive setup asks only for:

1. **Atlassian domain** (default: `ifsdev.atlassian.net`)
2. **Email** (Atlassian account)
3. **API token** — user is told to use their **Jira token** (works for Confluence on IFS)

Writes config + token. Does not download pages.

## `nova ask` — live Confluence search + AI

```
User question
    → GET /wiki/rest/api/content/search
         ?cql=text ~ "<query>"
         &limit=5
         &expand=body.storage
    → Basic Authorization: base64(email:jira_token)
    → Top hits → excerpts → AI prompt with Confluence context
    → Streamed answer
```

Implemented in `confluence_manager.search_confluence()` → `search_confluence_rest()`.

If `nova csetup` was not run, `nova ask` continues with **AI only** and prints a warning.

## `nova csync` — optional local index

Downloads pages from default spaces (`KAIROS`, `NGA`, `NEXUZ`, `NEXT`) into `~/.nova/confluence_index.json` for offline reference. Requires `nova csetup` first.

**`nova ask` does not use the local index**; it always uses live REST search when credentials exist.

## Module map

| Module | Role |
|--------|------|
| `nova_cli.py` | CLI: `csetup`, `csync`, `ask`, KB, AI |
| `confluence_manager.py` | Confluence sync, CQL REST search, token helpers |
| `config.py` | `~/.nova` paths, AI/KB config |
| `kb_manager.py` | Local/SharePoint KB |

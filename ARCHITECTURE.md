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

## `nova up` flow (Confluence → KB → AI)

Same order as `nova ask`.

1. Capture last terminal error (hooks)
2. **Confluence** — local BM25 search on error text; strong match → pages go to AI
3. **KB** — fuzzy search; strong match → show fix and **stop**
4. **AI** — Confluence+error prompt, else error-only; optional save to KB

Footer: `Pipeline: Confluence (…) → KB (…) → AI (…)`

## `nova ask` flow (Confluence → KB → AI)

1. Warn if `last_sync` > 7 days old
2. **Confluence** — BM25 search; top 5; weak → user pick; strong → pages for AI
3. **KB** — fuzzy search; ≥70% → show KB and **stop**; weaker matches → hints for AI
4. **AI** — Confluence excerpts (+ KB hints), or KB+AI, or general knowledge

Footer: `Pipeline: Confluence (…) → KB (…) → AI (…)`

## Scoring (local, no embeddings)

Search uses **BM25** over each page (title terms counted 3×) plus heuristic boosts:

| Layer | Role |
|--------|------|
| **BM25** | Corpus-aware ranking — rare terms (e.g. `kairos` in title) beat pages that only mention them once in long notes |
| **Heuristics** | Title/keyword/body word hits, WIP penalty, debug-in-title boost |
| **Phrases** | Full query phrase and bigrams in title get extra points |
| **Query expansion** | `debugger`→`debug`, `install`↔`setup`, common typos (`thorugh`→`through`) |

Displayed `score` is a combined value (BM25×100 + heuristics + phrase). Not comparable across different queries.

## Commands

| Command | Action |
|---------|--------|
| `nova csetup` | Credentials + optional NGA full scan |
| `nova csync -r` | Rescan NGA, show +new / ~updated |
| `nova ask` | Confluence → KB → AI |
| `nova up` | Confluence → KB → AI |

## Tests

`tests/` — `unittest` suite (run `bash run_tests.sh`). Uses a temp index file; no live Confluence calls except one mocked HTTP test for auth headers.

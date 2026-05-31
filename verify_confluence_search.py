#!/usr/bin/env python3
"""Verify Confluence RAG index search (reads --jira token from ./api if needed)."""
import os
import sys

_REPO = os.path.dirname(os.path.abspath(__file__))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from confluence_manager import (
    DEFAULT_DOMAIN,
    build_confluence_index,
    sample_index_entry,
    search_local_index,
    save_confluence_config,
    save_jira_token,
)


def _load_api_jira_token():
    api_path = os.path.join(_REPO, "api")
    if not os.path.isfile(api_path):
        return None, None
    in_section = False
    email = "thangaratnam.visakan@ifs.com"
    token = None
    for line in open(api_path, encoding="utf-8"):
        t = line.strip()
        if t == "--jira":
            in_section = True
            continue
        if in_section and t.startswith("--"):
            break
        if in_section and t.startswith("ATATT"):
            token = t
            break
    return email, token


def main():
    print("Sample index entry:")
    print(sample_index_entry())
    print()
    email, token = _load_api_jira_token()
    if not token:
        print("SKIP live scan: no --jira token in api")
        return 0
    domain = DEFAULT_DOMAIN
    save_confluence_config(email, domain=domain)
    save_jira_token(token)
    print("Building NGA index (live API)...")
    build_confluence_index(domain, email, token, space_key="NGA")
    print()
    print("search_local_index('install kairos'):")
    for i, r in enumerate(search_local_index("install kairos"), 1):
        print(f"  {i}. {r['title']} (score: {r['score']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

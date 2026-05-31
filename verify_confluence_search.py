#!/usr/bin/env python3
"""Verify Confluence CQL search (reads --jira token from ./api if ~/.nova not configured)."""
import os
import sys

_REPO = os.path.dirname(os.path.abspath(__file__))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from confluence_manager import (
    DEFAULT_DOMAIN,
    search_confluence_rest,
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
    email, token = _load_api_jira_token()
    if not token:
        print("SKIP: no --jira token in api and no ~/.nova setup")
        return 1
    domain = DEFAULT_DOMAIN
    print(f"GET https://{domain}/wiki/rest/api/content/search")
    print('  cql=text~"kairos"&limit=3&expand=body.storage')
    results = search_confluence_rest(domain, email, token, "kairos", top_n=3)
    if not results:
        print("FAIL: no results")
        return 1
    print(f"OK: {len(results)} result(s)")
    for i, r in enumerate(results, 1):
        print(f"  {i}. {r.get('title')}")
        print(f"     {r.get('url')}")
    save_confluence_config(email, domain=domain)
    save_jira_token(token)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Demo: sample index entry + scoring for 'install kairos' (offline)."""
import json
import sys

sys.path.insert(0, ".")
from confluence_manager import sample_index_entry, search_local_index, save_index_data, DEFAULT_DOMAIN

pages = [
    sample_index_entry(),
    {
        "id": "2",
        "title": "Deploy and Debug In Kairos",
        "url": "https://ifsdev.atlassian.net/wiki/spaces/NGA/pages/2",
        "space": "NGA",
        "full_text": "How to install kairos on staging and debug deployment failures step by step.",
        "keywords": ["deploy", "debug", "kairos", "staging", "install"],
        "summary": "How to install kairos on staging...",
        "last_updated": "2026-05-01T00:00:00Z",
    },
    {
        "id": "3",
        "title": "Kairos Team Member Onboarding",
        "url": "https://ifsdev.atlassian.net/wiki/spaces/NGA/pages/3",
        "space": "NGA",
        "full_text": "Onboarding guide for new engineers joining the kairos program.",
        "keywords": ["onboarding", "team", "kairos"],
        "summary": "Onboarding guide...",
        "last_updated": "2026-05-02T00:00:00Z",
    },
    {
        "id": "4",
        "title": "Setup Ubuntu in WSL2",
        "url": "https://ifsdev.atlassian.net/wiki/spaces/NGA/pages/4",
        "space": "NGA",
        "full_text": "Ubuntu WSL2 setup for local development environment.",
        "keywords": ["ubuntu", "wsl2", "setup"],
        "summary": "Ubuntu WSL2 setup...",
        "last_updated": "2026-05-03T00:00:00Z",
    },
    {
        "id": "5",
        "title": "CI/CD automation",
        "url": "https://ifsdev.atlassian.net/wiki/spaces/NGA/pages/5",
        "space": "NGA",
        "full_text": "Pipeline automation for continuous integration.",
        "keywords": ["cicd", "pipeline", "automation"],
        "summary": "Pipeline automation...",
        "last_updated": "2026-05-04T00:00:00Z",
    },
]

save_index_data(DEFAULT_DOMAIN, "NGA", pages)

print("=== Sample index entry ===")
print(json.dumps(sample_index_entry(), indent=2))
print()
print("=== search_local_index('install kairos') ===")
for i, r in enumerate(search_local_index("install kairos"), 1):
    print(f"  {i}. {r['title']} (score: {r['score']})")

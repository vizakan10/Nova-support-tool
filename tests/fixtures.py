"""Shared fixtures for offline Confluence RAG tests."""

SAMPLE_PAGES = [
    {
        "id": "1",
        "title": "NGA / Kairos Planning Page - Y26Q4",
        "url": "https://ifsdev.atlassian.net/wiki/spaces/NGA/pages/1/Planning",
        "space": "NGA",
        "full_text": "This page describes the Kairos deployment process for the NGA team.",
        "keywords": ["kairos", "deployment", "nga", "staging"],
        "summary": "Kairos deployment process for NGA.",
        "last_updated": "2026-05-15T10:30:00.000Z",
    },
    {
        "id": "2",
        "title": "Deploy and Debug In Kairos",
        "url": "https://ifsdev.atlassian.net/wiki/spaces/NGA/pages/2/Deploy+Debug",
        "space": "NGA",
        "full_text": (
            "Use VS Code to attach the Go debugger to Client API. "
            "Open launch.json and use the Client API configuration. "
            "See kubectl port-forward steps for local cluster."
        ),
        "keywords": ["deploy", "debug", "kairos", "vscode", "go"],
        "summary": "Deploy and debug Kairos apps in VS Code.",
        "last_updated": "2026-05-16T10:30:00.000Z",
    },
    {
        "id": "3",
        "title": "WIP: Kairos-ADR-16: Mobile Application Framework",
        "url": "https://ifsdev.atlassian.net/wiki/spaces/NGA/pages/3/ADR-16",
        "space": "NGA",
        "full_text": "Draft ADR for mobile framework. Mentions kairos and debug logging.",
        "keywords": ["kairos", "mobile", "adr"],
        "summary": "Draft mobile ADR.",
        "last_updated": "2026-05-17T10:30:00.000Z",
    },
    {
        "id": "4",
        "title": "Kairos QuickStart Guide",
        "url": "https://ifsdev.atlassian.net/wiki/spaces/NGA/pages/4/QuickStart",
        "space": "NGA",
        "full_text": "Install Kairos CLI, run setup script, create local cluster with kairos-cli.",
        "keywords": ["kairos", "install", "quickstart", "wsl"],
        "summary": "Install Kairos locally.",
        "last_updated": "2026-05-18T10:30:00.000Z",
    },
    {
        "id": "5",
        "title": "App Teams - Onboarding to Kairos",
        "url": "https://ifsdev.atlassian.net/wiki/spaces/NGA/pages/5/Onboarding",
        "space": "NGA",
        "full_text": "Onboarding checklist for app teams joining Kairos.",
        "keywords": ["onboarding", "kairos", "teams"],
        "summary": "App team onboarding.",
        "last_updated": "2026-05-19T10:30:00.000Z",
    },
]

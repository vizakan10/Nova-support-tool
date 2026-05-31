#!/usr/bin/env python3
"""Unit tests for confluence_manager (offline RAG search + auth helpers)."""

import base64
import os
import sys
import tempfile
import unittest
from unittest import mock

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

import confluence_manager as cm
from tests.fixtures import SAMPLE_PAGES


class ConfluenceIndexTestCase(unittest.TestCase):
    """Tests that need a temporary index file."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._index_path = os.path.join(self._tmp.name, "confluence_index.json")
        patcher = mock.patch.object(cm, "CONFLUENCE_INDEX_FILE", self._index_path)
        self.addCleanup(patcher.stop)
        patcher.start()
        cm.save_index_data(cm.DEFAULT_DOMAIN, "NGA", list(SAMPLE_PAGES))

    def test_search_install_kairos_prefers_quickstart_or_deploy(self):
        results = cm.search_local_index("install kairos", top_n=5)
        self.assertGreaterEqual(len(results), 2)
        titles = [r["title"] for r in results]
        self.assertIn("Kairos QuickStart Guide", titles)
        top = results[0]["title"]
        self.assertIn(
            top,
            ("Kairos QuickStart Guide", "Deploy and Debug In Kairos", "NGA / Kairos Planning Page - Y26Q4"),
        )

    def test_bm25_quickstart_beats_generic_onboarding_for_install(self):
        results = cm.search_local_index("install kairos", top_n=5)
        by_title = {r["title"]: r["score"] for r in results}
        self.assertGreater(
            by_title.get("Kairos QuickStart Guide", 0),
            by_title.get("App Teams - Onboarding to Kairos", 0),
        )

    def test_sort_ranked_debug_puts_deploy_and_debug_first(self):
        pool = cm.search_local_index(
            "debug kairos app through vscode debugger", top_n=15
        )
        ordered = cm.sort_ranked_for_query(pool, "debug kairos app through vscode debugger")
        self.assertGreater(len(ordered), 0)
        self.assertEqual(ordered[0]["title"], "Deploy and Debug In Kairos")

    def test_select_pages_uses_single_page_when_clear_winner(self):
        pool = cm.search_local_index(
            "debug kairos vscode", top_n=15
        )
        pages = cm.select_pages_for_ai_context(
            pool, "debug kairos vscode", top_n=3
        )
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0]["title"], "Deploy and Debug In Kairos")

    def test_wip_page_ranks_below_deploy_for_debug_query(self):
        pool = cm.search_local_index("debug kairos", top_n=15)
        ordered = cm.sort_ranked_for_query(pool, "debug kairos")
        wip_idx = next(
            i for i, p in enumerate(ordered) if p["title"].startswith("WIP:")
        )
        deploy_idx = next(
            i for i, p in enumerate(ordered)
            if p["title"] == "Deploy and Debug In Kairos"
        )
        self.assertLess(deploy_idx, wip_idx)


class ConfluenceHelpersTestCase(unittest.TestCase):
    def test_auth_header_uses_basic_prefix(self):
        hdr = cm._auth_header("user@ifs.com", "secret-token")
        self.assertTrue(hdr.startswith("Basic "))
        decoded = base64.b64decode(hdr[6:]).decode("utf-8")
        self.assertEqual(decoded, "user@ifs.com:secret-token")

    def test_normalize_domain_strips_scheme(self):
        self.assertEqual(
            cm._normalize_domain("https://ifsdev.atlassian.net/"),
            "ifsdev.atlassian.net",
        )

    def test_format_confluence_api_error_403(self):
        msg = cm.format_confluence_api_error(
            403,
            '{"message":"Current user not permitted to use Confluence"}',
            email="user@ifs.com",
        )
        self.assertIn("Confluence API denied", msg)
        self.assertIn("classic API token", msg)

    def test_format_confluence_api_error_401(self):
        msg = cm.format_confluence_api_error(401, "Unauthorized")
        self.assertIn("authentication failed", msg.lower())

    def test_html_to_text_strips_tags(self):
        text = cm._html_to_text("<p>Hello <b>Kairos</b> &amp; team</p>")
        self.assertEqual(text, "Hello Kairos & team")

    def test_split_query_words_skips_stopwords(self):
        words = cm.split_query_words("i want to install kairos")
        self.assertIn("install", words)
        self.assertIn("kairos", words)
        self.assertNotIn("want", words)

    def test_split_query_words_fixes_common_typos(self):
        words = cm.split_query_words("how to instal kairos")
        self.assertIn("install", words)

    def test_expand_query_terms_links_install_and_setup(self):
        terms = cm.expand_query_terms(["install"])
        self.assertIn("install", terms)
        self.assertIn("setup", terms)

    def test_word_matches_text_debugger_matches_debug(self):
        self.assertTrue(cm._word_matches_text("debugger", "deploy and debug in kairos"))

    def test_pages_for_ai_context_respects_total_char_limit(self):
        ranked = [{"title": "A", "full_text": "x" * 10000, "score": 10}]
        out = cm.pages_for_ai_context(
            ranked, top_n=1, char_limit_per_page=5000, total_char_limit=3000
        )
        self.assertLessEqual(len(out[0]["excerpt"]), 3000)

    def test_load_index_legacy_list_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "index.json")
            import json

            with open(path, "w", encoding="utf-8") as fh:
                json.dump(SAMPLE_PAGES[:2], fh)
            with mock.patch.object(cm, "CONFLUENCE_INDEX_FILE", path):
                data = cm.load_index_data()
            self.assertEqual(data["page_count"], 2)
            self.assertEqual(len(data["pages"]), 2)

    def test_verify_confluence_access_requires_credentials(self):
        ok, err = cm.verify_confluence_access("", "", "")
        self.assertFalse(ok)
        self.assertIn("required", err.lower())


class ConfluenceApiMockTestCase(unittest.TestCase):
    def test_confluence_get_sets_authorization_header(self):
        captured = {}

        def fake_urlopen(req, timeout=120):
            captured["auth"] = req.get_header("Authorization")
            captured["url"] = req.full_url

            class Resp:
                def read(self):
                    return b'{"results":[]}'

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    pass

            return Resp()

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            cm._confluence_get(
                "ifsdev.atlassian.net",
                "user@ifs.com",
                "tok",
                "content?spaceKey=NGA&limit=1",
                timeout=5,
            )
        self.assertTrue(captured["auth"].startswith("Basic "))
        self.assertIn("/wiki/rest/api/content", captured["url"])


if __name__ == "__main__":
    unittest.main()

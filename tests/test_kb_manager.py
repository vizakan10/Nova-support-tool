#!/usr/bin/env python3
"""Unit tests for kb_manager fuzzy search."""

import os
import sys
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from kb_manager import fuzzy_search


SAMPLE_KB = [
    {
        "id": "1",
        "error": "ModuleNotFoundError: No module named 'requests'",
        "solution": "pip install requests",
        "command": "pip install requests",
    },
    {
        "id": "2",
        "error": "npm ERR! code ELIFECYCLE",
        "solution": "Delete node_modules and run npm install",
        "command": "rm -rf node_modules && npm install",
    },
    {
        "id": "3",
        "error": "kairos: command not found",
        "solution": "Run kairos-cli setup from the repo root",
        "command": "./kairos-cli setup",
    },
]


class FuzzySearchTestCase(unittest.TestCase):
    def test_empty_query_returns_empty(self):
        self.assertEqual(fuzzy_search("", SAMPLE_KB), [])
        self.assertEqual(fuzzy_search("error", []), [])

    def test_finds_kairos_command_error(self):
        results = fuzzy_search("kairos command not found", SAMPLE_KB, threshold=55)
        self.assertGreaterEqual(len(results), 1)
        self.assertIn("kairos", results[0][0]["error"].lower())

    def test_module_not_found_requires_module_match(self):
        results = fuzzy_search(
            "ModuleNotFoundError: No module named 'requests'",
            SAMPLE_KB,
            threshold=70,
        )
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0][0]["id"], "1")

    def test_unrelated_module_not_matched_at_high_threshold(self):
        results = fuzzy_search(
            "ModuleNotFoundError: No module named 'flask'",
            SAMPLE_KB,
            threshold=70,
        )
        self.assertEqual(len(results), 0)

    def test_results_sorted_by_score_descending(self):
        results = fuzzy_search("npm install failed", SAMPLE_KB, threshold=40)
        if len(results) >= 2:
            self.assertGreaterEqual(results[0][1], results[1][1])


if __name__ == "__main__":
    unittest.main()

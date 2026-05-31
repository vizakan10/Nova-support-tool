#!/usr/bin/env python3
"""Unit tests for nova ask helpers (answer polish, KB context formatting)."""

import os
import sys
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

import nova_cli


class PolishAskAnswerTestCase(unittest.TestCase):
    def test_polish_removes_stopon_spam(self):
        raw = "\n".join([
            "## Summary",
            "Debug using VS Code.",
            '"stopOnEntry": false',
            '"stopOnCrash": false',
        ])
        out = nova_cli._polish_ask_answer(raw)
        self.assertNotIn("stopOnEntry", out)
        self.assertIn("Summary", out)

    def test_polish_dedupes_repeated_lines(self):
        raw = "line one\nline one\nline one\nunique\n"
        out = nova_cli._polish_ask_answer(raw)
        self.assertEqual(out.count("line one"), 1)

    def test_polish_truncates_very_long_answer(self):
        raw = "x" * 4000
        out = nova_cli._polish_ask_answer(raw)
        self.assertLess(len(out), 3500)
        self.assertIn("trimmed", out)

    def test_polish_omits_huge_code_fence(self):
        lines = ["## Steps", "```json", "{"] + ['  "k": v,' for v in range(40)] + ["```"]
        raw = "\n".join(lines)
        out = nova_cli._polish_ask_answer(raw)
        self.assertIn("omitted", out)

    def test_polish_empty_returns_empty(self):
        self.assertEqual(nova_cli._polish_ask_answer(""), "")
        self.assertEqual(nova_cli._polish_ask_answer(None), None)


class FormatKbSectionTestCase(unittest.TestCase):
    def test_format_kb_section_includes_match_scores(self):
        entry = {"error": "pip install failed", "solution": "Use python3 -m pip"}
        section = nova_cli._format_kb_section_for_ai([(entry, 82)])
        self.assertIn("82%", section)
        self.assertIn("pip install failed", section)
        self.assertIn("python3 -m pip", section)

    def test_format_kb_section_empty(self):
        self.assertEqual(nova_cli._format_kb_section_for_ai([]), "")


class ConfluenceAskPromptTestCase(unittest.TestCase):
    def test_confluence_prompt_requires_summary_and_steps(self):
        self.assertIn("## Summary", nova_cli._AI_CONFLUENCE_ASK_PROMPT)
        self.assertIn("## Steps", nova_cli._AI_CONFLUENCE_ASK_PROMPT)
        self.assertIn("## Reference", nova_cli._AI_CONFLUENCE_ASK_PROMPT)
        self.assertIn("Do NOT paste large config", nova_cli._AI_CONFLUENCE_ASK_PROMPT)


if __name__ == "__main__":
    unittest.main()

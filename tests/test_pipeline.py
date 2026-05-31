#!/usr/bin/env python3
"""Verify nova up / nova ask include KB, Confluence, and AI in the correct order."""

import os
import sys
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

import nova_cli as nc


class PipelineOrderTestCase(unittest.TestCase):
    def test_up_pipeline_order(self):
        self.assertEqual(nc.UP_PIPELINE_ORDER, ("Confluence", "KB", "AI"))
        self.assertEqual(nc.UP_PIPELINE_ORDER, nc.ASK_PIPELINE_ORDER)

    def test_ask_pipeline_order(self):
        self.assertEqual(nc.ASK_PIPELINE_ORDER, ("Confluence", "KB", "AI"))

    def test_fresh_pipeline_starts_skipped(self):
        trail = nc._fresh_pipeline(nc.UP_PIPELINE_ORDER)
        self.assertEqual(trail["KB"], "skip")
        self.assertEqual(trail["Confluence"], "skip")
        self.assertEqual(trail["AI"], "skip")

    def test_cmd_up_docstring_declares_three_sources(self):
        self.assertIn("KB", nc.cmd_up.__doc__)
        self.assertIn("Confluence", nc.cmd_up.__doc__)
        self.assertIn("AI", nc.cmd_up.__doc__)

    def test_cmd_ask_docstring_declares_three_sources(self):
        self.assertIn("Confluence", nc.cmd_ask.__doc__)
        self.assertIn("KB", nc.cmd_ask.__doc__)
        self.assertIn("AI", nc.cmd_ask.__doc__)


if __name__ == "__main__":
    unittest.main()

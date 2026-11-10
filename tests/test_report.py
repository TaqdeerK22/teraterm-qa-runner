import csv
import io
import unittest

import helpers
from qa_runner.model import Result
from qa_runner.report import render_csv, render_html, render_markdown, render_text, summarize
from qa_runner.suite import load_suite


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.suite = load_suite(helpers.DEMO_SUITE)
        self.results = {
            "BOOT-001": Result("PASS"), "BOOT-002": Result("PASS"), "BOOT-003": Result("PASS"),
            "NET-001": Result("FAIL", "no <lease> | slow"), "NET-002": Result("BLOCKED", "no cable"),
            "LED-001": Result("SKIP"),
        }
        self.summary = summarize(self.suite, self.results)

    def test_counts_and_rates(self):
        s = self.summary
        self.assertEqual(s.counts, {"PASS": 3, "FAIL": 1, "BLOCKED": 1, "SKIP": 1, "NOT RUN": 6})
        self.assertEqual((s.total, s.executed), (12, 6))
        self.assertAlmostEqual(s.progress, 0.5)
        self.assertAlmostEqual(s.pass_rate, 0.75)

    def test_pass_rate_undefined_without_decisions(self):
        self.assertIsNone(summarize(self.suite, {}).pass_rate)

    def test_group_breakdown_and_attention_list(self):
        groups = dict(self.summary.by_group)
        self.assertEqual(groups["Startup"]["PASS"], 3)
        self.assertEqual(groups["Connectivity"]["FAIL"], 1)
        self.assertEqual([t.id for t, _ in self.summary.attention], ["NET-001", "NET-002"])

    def test_text(self):
        text = render_text(self.summary)
        self.assertIn("Pass rate: 75.0%", text)
        self.assertIn("[FAIL] NET-001", text)

    def test_markdown_escapes_pipes(self):
        md = render_markdown(self.summary)
        self.assertIn("no <lease> \\| slow", md)
        self.assertIn("| Startup |", md)

    def test_html_escapes_content(self):
        html = render_html(self.summary, self.results)
        self.assertIn("no &lt;lease&gt; | slow", html)
        self.assertNotIn("<lease>", html)
        self.assertIn("class=\"b FAIL\"", html)
        self.assertIn("NOT_RUN", html)

    def test_csv_roundtrips_and_quotes(self):
        rows = list(csv.reader(io.StringIO(render_csv(self.suite, self.results))))
        self.assertEqual(rows[0][0], "ID")
        self.assertEqual(len(rows), 13)
        self.assertEqual(rows[4][3:5], ["FAIL", "no <lease> | slow"])


if __name__ == "__main__":
    unittest.main()

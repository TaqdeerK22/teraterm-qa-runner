import re
import unittest

import helpers
from qa_runner.model import STATUSES
from qa_runner.suite import load_suite, parse_suite
from qa_runner.ttl import MacroOptions, generate_macro, lint, quote


def macro_for(raw=None, **opts):
    suite = parse_suite(raw) if raw else load_suite(helpers.DEMO_SUITE)
    return suite, generate_macro(suite, MacroOptions(suite_rel_path="..\\suites\\x.json", **opts))


class QuoteTests(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(quote("hello world"), "'hello world'")

    def test_empty(self):
        self.assertEqual(quote(""), "''")

    def test_apostrophes_use_char_code(self):
        self.assertEqual(quote("it's"), "'it'#39's'")
        self.assertEqual(quote("'x'"), "#39'x'#39")
        self.assertEqual(quote("''"), "#39#39")

    def test_non_ascii_and_control_rejected(self):
        for bad in ("caf\u00e9", "a\nb", "tab\t"):
            with self.assertRaises(ValueError):
                quote(bad)

    def test_double_quotes_and_backslashes_pass_through(self):
        self.assertEqual(quote('say "hi" C:\\x'), "'say \"hi\" C:\\x'")


class GeneratedMacroTests(unittest.TestCase):
    def test_demo_macro_is_lint_clean(self):
        _, macro = macro_for()
        self.assertEqual(lint(macro), [])

    def test_every_test_recorded_exactly_once_in_order(self):
        suite, macro = macro_for()
        ids = re.findall(r"^qa_id = '([^']+)'$", macro, re.M)
        self.assertEqual(ids, suite.test_ids())

    def test_subroutines_come_after_end(self):
        _, macro = macro_for()
        lines = macro.splitlines()
        self.assertLess(lines.index("end"), lines.index(":qa_record"))
        self.assertEqual(lines.count("end"), 1)

    def test_status_prompt_and_matching_come_from_the_model(self):
        _, macro = macro_for()
        for s in STATUSES:
            self.assertIn(f"qa_short = '{s.key}'\nqa_full = '{s.name}'\ncall qa_match", macro)

    def test_secret_value_is_never_in_the_macro(self):
        _, macro = macro_for()
        self.assertIn("passwordbox 'Device admin password'", macro)
        self.assertIn("sprintf2 qa_cmd 'login admin %s' inputstr", macro)

    def test_percent_signs_in_secret_commands_are_escaped(self):
        raw = helpers.minimal_suite_dict()
        raw["setup"] = [{"send_secret": "auth 100% {secret}"}]
        _, macro = macro_for(raw)
        self.assertIn("'auth 100%% %s'", macro)

    def test_apostrophes_in_text_survive(self):
        raw = helpers.minimal_suite_dict()
        raw["tests"][0]["verify"] = "Verify it's on."
        _, macro = macro_for(raw)
        self.assertIn("'Verify it'#39's on.'", macro)
        self.assertEqual(lint(macro), [])

    def test_wait_zero_emits_no_pause(self):
        raw = helpers.minimal_suite_dict()
        raw["tests"][0]["steps"] = [{"send": "a", "wait_after": 0}, {"wait": 0}]
        _, macro = macro_for(raw)
        self.assertNotIn("pause 0\npause 0", macro)
        self.assertIn("sendln 'a'\n", macro)

    def test_subset_generation(self):
        suite = load_suite(helpers.DEMO_SUITE)
        subset = [suite.tests[3], suite.tests[0]]
        macro = generate_macro(suite, MacroOptions("..\\s.json", tests=subset))
        self.assertEqual(re.findall(r"^qa_id = '([^']+)'$", macro, re.M), ["NET-001", "BOOT-001"])
        self.assertIn("; Tests : 2 of 12", macro)

    def test_settings_are_overridable(self):
        _, macro = macro_for(python_cmd="python", results_dir_name="my_results")
        self.assertIn("qa_python = 'python'", macro)
        self.assertIn("qa_results_name = 'my_results'", macro)

    def test_only_ascii_and_lf(self):
        _, macro = macro_for()
        macro.encode("ascii")
        self.assertNotIn("\r", macro)

    def test_generation_is_deterministic(self):
        self.assertEqual(macro_for()[1], macro_for()[1])


class LintTests(unittest.TestCase):
    def test_detects_problems(self):
        bad = "if a = 1 then\ngoto nowhere\n:x\n:x\ncall qa_record\n"
        problems = "\n".join(lint(bad))
        for expected in ("mismatch", "undefined label nowhere", "duplicate label x",
                         "must follow", "no 'end'"):
            self.assertIn(expected, problems)

    def test_detects_unbalanced_quote(self):
        self.assertTrue(any("quote" in p for p in lint("messagebox 'oops\nend\n")))


if __name__ == "__main__":
    unittest.main()

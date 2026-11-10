import unittest

import helpers  # noqa: F401
from qa_runner.model import STATUS_NAMES, normalize_status


class NormalizeStatusTests(unittest.TestCase):
    def test_letters_and_names_any_case(self):
        for text, expected in [("p", "PASS"), ("PASS", "PASS"), ("Fail", "FAIL"), ("f", "FAIL"),
                               ("b", "BLOCKED"), ("s", "SKIP"), ("n", "NOT RUN"),
                               ("not run", "NOT RUN"), ("  Not   Run ", "NOT RUN")]:
            self.assertEqual(normalize_status(text), expected, text)

    def test_underscore_form_for_command_line(self):
        self.assertEqual(normalize_status("not_run"), "NOT RUN")

    def test_rejects_junk_and_empty(self):
        for text in ("", "x", "passed", "pas", "maybe"):
            self.assertIsNone(normalize_status(text), text)

    def test_keys_are_unique(self):
        from qa_runner.model import STATUSES
        self.assertEqual(len({s.key for s in STATUSES}), len(STATUSES))
        self.assertEqual(len(set(STATUS_NAMES)), len(STATUS_NAMES))


if __name__ == "__main__":
    unittest.main()

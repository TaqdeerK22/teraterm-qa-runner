import json
import tempfile
import unittest
from pathlib import Path

import helpers
from qa_runner.suite import SuiteError, load_suite, parse_suite, select_tests


class DemoSuiteTests(unittest.TestCase):
    def test_demo_suite_is_valid(self):
        suite = load_suite(helpers.DEMO_SUITE)
        self.assertEqual(suite.id, "widget-demo")
        self.assertEqual(len(suite.tests), 12)
        self.assertEqual(suite.groups(), ["Startup", "Connectivity", "Indicators", "Storage"])
        self.assertEqual(len(suite.setup), 2)
        self.assertEqual(len(suite.teardown), 2)

    def test_default_wait_is_applied_to_commands(self):
        suite = load_suite(helpers.DEMO_SUITE)
        self.assertEqual(suite.tests[0].steps[0].seconds, 2)   # inherited default_wait
        self.assertEqual(suite.tests[4].steps[1].seconds, 5)   # explicit wait_after

    def test_load_file_errors(self):
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "bad.json"
            bad.write_text("{not json", encoding="utf-8")
            with self.assertRaises(SuiteError) as ctx:
                load_suite(bad)
            self.assertIn("not valid JSON", ctx.exception.errors[0])


class ValidationTests(unittest.TestCase):
    def errors(self, raw):
        with self.assertRaises(SuiteError) as ctx:
            parse_suite(raw)
        return ctx.exception.errors

    def test_minimal_suite_parses(self):
        suite = parse_suite(helpers.minimal_suite_dict())
        self.assertEqual(suite.tests[0].group, "General")

    def test_collects_every_problem_at_once(self):
        raw = helpers.minimal_suite_dict(id="bad id!", name="")
        raw["tests"].append({"id": "T-1", "title": "dup", "verify": ""})
        errors = self.errors(raw)
        self.assertGreaterEqual(len(errors), 4)
        self.assertTrue(any(e.startswith("id:") for e in errors))
        self.assertTrue(any("duplicate" in e for e in errors))

    def test_tests_required(self):
        self.assertTrue(any("tests" in e for e in self.errors(helpers.minimal_suite_dict(tests=[]))))

    def test_non_ascii_macro_text_rejected(self):
        raw = helpers.minimal_suite_dict()
        raw["tests"][0]["verify"] = "Caf\u00e9 must be hot"
        self.assertTrue(any("ASCII" in e for e in self.errors(raw)))

    def test_text_length_limit(self):
        raw = helpers.minimal_suite_dict()
        raw["tests"][0]["verify"] = "x" * 400
        self.assertTrue(any("longer than" in e for e in self.errors(raw)))

    def test_step_needs_exactly_one_kind(self):
        raw = helpers.minimal_suite_dict()
        raw["tests"][0]["steps"] = [{"send": "a", "instruct": "b"}, {}, {"nope": 1}, "text"]
        errors = self.errors(raw)
        self.assertEqual(sum("exactly one" in e for e in errors), 3)
        self.assertTrue(any("must be an object" in e for e in errors))

    def test_unknown_step_key_is_reported(self):
        raw = helpers.minimal_suite_dict()
        raw["tests"][0]["steps"] = [{"send": "a", "waits": 2}]
        self.assertTrue(any("unknown key 'waits'" in e for e in self.errors(raw)))

    def test_wait_must_be_sane_integer(self):
        for bad in (-1, 99999, "3", 1.5, True):
            raw = helpers.minimal_suite_dict()
            raw["tests"][0]["steps"] = [{"wait": bad}]
            self.assertTrue(self.errors(raw), bad)

    def test_secret_template_needs_one_placeholder(self):
        for template in ("login admin", "login {secret} {secret}"):
            raw = helpers.minimal_suite_dict()
            raw["tests"][0]["steps"] = [{"send_secret": template}]
            self.assertTrue(any("{secret}" in e for e in self.errors(raw)), template)

    def test_schema_version_checked(self):
        self.assertTrue(any("schema" in e for e in self.errors(helpers.minimal_suite_dict(schema=2))))

    def test_top_level_must_be_object(self):
        self.assertTrue(self.errors([1, 2]))

    def test_json_roundtrip_does_not_matter(self):
        raw = json.loads(json.dumps(helpers.minimal_suite_dict()))
        self.assertEqual(parse_suite(raw).id, "t")


class SelectTests(unittest.TestCase):
    def setUp(self):
        self.suite = load_suite(helpers.DEMO_SUITE)

    def ids(self, **kw):
        return [t.id for t in select_tests(self.suite, **kw)]

    def test_all_by_default(self):
        self.assertEqual(len(self.ids()), 12)

    def test_by_ids_preserves_suite_order(self):
        self.assertEqual(self.ids(ids=["NET-002", "BOOT-001"]), ["BOOT-001", "NET-002"])

    def test_by_group(self):
        self.assertEqual(self.ids(group="Indicators"), ["LED-001", "LED-002"])

    def test_start_at(self):
        self.assertEqual(self.ids(start_at="STO-001"), ["STO-001", "STO-002", "STO-003"])

    def test_combined(self):
        self.assertEqual(self.ids(group="Storage", start_at="STO-002"), ["STO-002", "STO-003"])

    def test_unknowns_and_empty(self):
        for kw in ({"ids": ["NOPE"]}, {"group": "Nope"}, {"start_at": "NOPE"},
                   {"group": "Storage", "start_at": "BOOT-001"}, {"ids": []}):
            with self.assertRaises(SuiteError, msg=str(kw)):
                select_tests(self.suite, **kw)


if __name__ == "__main__":
    unittest.main()

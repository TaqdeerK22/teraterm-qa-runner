import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import helpers
from qa_runner.cli import main
from qa_runner.model import Result
from qa_runner.suite import load_suite
from qa_runner.xlsx import read_results, write_workbook

SUITE = str(helpers.DEMO_SUITE)


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(list(argv))
        except SystemExit as exc:           # argparse errors
            code = exc.code
    return code, out.getvalue(), err.getvalue()


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_validate_ok_and_invalid(self):
        code, out, _ = run("validate", SUITE)
        self.assertEqual(code, 0)
        self.assertIn("12 tests", out)
        bad = self.dir / "bad.json"
        bad.write_text('{"id": "x y", "tests": []}', encoding="utf-8")
        code, _, err = run("validate", str(bad))
        self.assertEqual(code, 2)
        self.assertIn("problems", err)

    def test_missing_file_is_a_clean_error(self):
        code, _, err = run("validate", str(self.dir / "nope.json"))
        self.assertEqual(code, 2)
        self.assertIn("error:", err)

    def test_generate_writes_clean_macro_with_relative_suite_path(self):
        out = self.dir / "dist" / "demo.ttl"
        code, msg, _ = run("generate", SUITE, "-o", str(out))
        self.assertEqual(code, 0)
        self.assertIn("12 of 12", msg)
        text = out.read_text(encoding="ascii")
        self.assertIn("qa_suite_rel = '", text)
        self.assertIn("suites\\demo_suite.json'", text)
        self.assertNotIn(str(self.dir), text)             # no absolute paths leak into the macro

    def test_generate_filters(self):
        out = self.dir / "m.ttl"
        self.assertEqual(run("generate", SUITE, "-o", str(out), "--group", "Storage")[0], 0)
        self.assertIn("3 of 12", run("generate", SUITE, "-o", str(out), "--group", "Storage")[1])
        self.assertEqual(run("generate", SUITE, "-o", str(out), "--ids", "NOPE")[0], 2)

    def test_generate_rerun_from_results(self):
        suite = load_suite(SUITE)
        book = self.dir / "b.xlsx"
        done = {t.id: Result("PASS") for t in suite.tests}
        done["NET-002"] = Result("FAIL")
        done["STO-003"] = Result("NOT RUN")
        del done["LED-002"]                                  # never recorded = NOT RUN
        write_workbook(book, suite, done, "t")
        out = self.dir / "rerun.ttl"
        code, msg, _ = run("generate", SUITE, "-o", str(out), "--results", str(book),
                           "--only-status", "FAIL,not_run")
        self.assertEqual(code, 0, msg)
        self.assertIn("3 of 12", msg)
        text = out.read_text(encoding="ascii")
        for tid in ("NET-002", "LED-002", "STO-003"):
            self.assertIn(f"qa_id = '{tid}'", text)
        self.assertNotIn("qa_id = 'BOOT-001'", text)

    def test_only_status_validation(self):
        out = str(self.dir / "m.ttl")
        self.assertEqual(run("generate", SUITE, "-o", out, "--only-status", "FAIL")[0], 2)
        book = self.dir / "b.xlsx"
        run("init", SUITE, str(book))
        self.assertEqual(run("generate", SUITE, "-o", out, "--results", str(book),
                             "--only-status", "weird")[0], 2)
        # nothing FAILED yet -> empty selection is reported, not an empty macro
        code, _, err = run("generate", SUITE, "-o", out, "--results", str(book), "--only-status", "FAIL")
        self.assertEqual(code, 2)
        self.assertIn("no tests", err)

    def test_init_refuses_to_overwrite(self):
        book = str(self.dir / "b.xlsx")
        self.assertEqual(run("init", SUITE, book)[0], 0)
        self.assertEqual(run("init", SUITE, book)[0], 2)
        self.assertEqual(run("init", SUITE, book, "--force")[0], 0)

    def test_record_and_report_end_to_end(self):
        pending, book = self.dir / "p.txt", self.dir / "b.xlsx"
        pending.write_bytes(b"NET-001\r\nf\r\nAnn\r\nlink down\r\n")
        code, out, _ = run("record", SUITE, str(pending), str(book))
        self.assertEqual((code, out.strip()), (0, "saved NET-001 = FAIL"))
        self.assertEqual(read_results(book)["NET-001"].comment, "link down")

        code, out, _ = run("report", SUITE, str(book))
        self.assertEqual(code, 0)
        self.assertIn("[FAIL] NET-001", out)
        self.assertEqual(run("report", SUITE, str(book), "--fail-on-fail")[0], 1)

        for fmt, needle in (("md", "# Acme"), ("html", "<!doctype html>"), ("csv", "NET-001,Connectivity")):
            target = self.dir / f"r.{fmt}"
            self.assertEqual(run("report", SUITE, str(book), "--format", fmt, "-o", str(target))[0], 0)
            self.assertIn(needle, target.read_text(encoding="utf-8"))

    def test_record_failure_logs_and_keeps_pending(self):
        pending, book = self.dir / "p.txt", self.dir / "b.xlsx"
        pending.write_bytes(b"NET-001\r\nmaybe\r\nAnn\r\n")
        code, _, err = run("record", SUITE, str(pending), str(book))
        self.assertEqual(code, 1)
        self.assertIn("invalid status", err)
        self.assertTrue(pending.exists())
        self.assertIn("invalid status", (self.dir / "qa_runner_error.log").read_text(encoding="utf-8"))

    def test_no_command_is_a_usage_error(self):
        self.assertEqual(run()[0], 2)

    def test_python_dash_m_entry_point(self):
        import subprocess
        import sys
        proc = subprocess.run([sys.executable, "-m", "qa_runner", "--version"], capture_output=True,
                              text=True, env={"PYTHONPATH": str(helpers.ROOT / "src")})
        self.assertEqual(proc.returncode, 0)
        self.assertIn("qa-runner 1.0.0", proc.stdout)


if __name__ == "__main__":
    unittest.main()

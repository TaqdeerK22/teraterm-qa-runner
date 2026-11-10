import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers
from qa_runner import results as results_mod
from qa_runner.results import PendingError, log_error, parse_pending, record
from qa_runner.suite import load_suite
from qa_runner.xlsx import read_results


def pending_bytes(*lines, encoding="cp1252"):
    return ("\r\n".join(lines) + "\r\n").encode(encoding)


class ParsePendingTests(unittest.TestCase):
    def setUp(self):
        self.suite = load_suite(helpers.DEMO_SUITE)

    def test_basic(self):
        p = parse_pending(pending_bytes("BOOT-001", "pass", "Ann", "looks good"), self.suite)
        self.assertEqual((p.test_id, p.status, p.tester, p.comment),
                         ("BOOT-001", "PASS", "Ann", "looks good"))

    def test_ansi_text_from_tera_term(self):
        raw = pending_bytes("BOOT-001", "FAIL", "Ren\u00e9", "Caf\u00e9 5 \u00b0C", encoding="cp1252")
        p = parse_pending(raw, self.suite)
        self.assertEqual((p.tester, p.comment), ("Ren\u00e9", "Caf\u00e9 5 \u00b0C"))

    def test_utf8_with_bom_also_works(self):
        raw = "\ufeffBOOT-001\nPASS\nAnn\nok\u2713\n".encode("utf-8")
        self.assertEqual(parse_pending(raw, self.suite).comment, "ok\u2713")

    def test_empty_comment_and_multiline_comment(self):
        self.assertEqual(parse_pending(pending_bytes("BOOT-001", "PASS", "A", ""), self.suite).comment, "")
        self.assertEqual(parse_pending(pending_bytes("BOOT-001", "PASS", "A", "l1", "l2"), self.suite).comment,
                         "l1\nl2")

    def test_rejects_bad_input(self):
        for raw in (b"", b"BOOT-001\nPASS\n", pending_bytes("NOPE-1", "PASS", "A", ""),
                    pending_bytes("BOOT-001", "maybe", "A", "")):
            with self.assertRaises(PendingError):
                parse_pending(raw, self.suite)

    def test_tester_is_length_limited(self):
        p = parse_pending(pending_bytes("BOOT-001", "PASS", "x" * 500, ""), self.suite)
        self.assertEqual(len(p.tester), 100)


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.pending = self.dir / "_pending.txt"
        self.book = self.dir / "book.xlsx"
        self.suite = load_suite(helpers.DEMO_SUITE)

    def write_pending(self, *lines):
        self.pending.write_bytes(pending_bytes(*lines))

    def test_creates_workbook_and_removes_pending(self):
        self.write_pending("NET-001", "PASS", "Ann", "ok")
        record(self.suite, self.pending, self.book, now="2026-02-03T04:05:06Z")
        self.assertFalse(self.pending.exists())
        r = read_results(self.book)["NET-001"]
        self.assertEqual((r.status, r.comment, r.tester, r.recorded_at),
                         ("PASS", "ok", "Ann", "2026-02-03T04:05:06Z"))

    def test_merges_and_overwrites(self):
        for tid, status in (("NET-001", "PASS"), ("NET-002", "FAIL"), ("NET-001", "BLOCKED")):
            self.write_pending(tid, status, "Ann", "")
            record(self.suite, self.pending, self.book)
        got = read_results(self.book)
        self.assertEqual((got["NET-001"].status, got["NET-002"].status), ("BLOCKED", "FAIL"))

    def test_invalid_pending_keeps_file_and_workbook_untouched(self):
        self.write_pending("NET-001", "PASS", "Ann", "")
        record(self.suite, self.pending, self.book)
        before = self.book.read_bytes()
        self.write_pending("NET-001", "bogus", "Ann", "")
        with self.assertRaises(PendingError):
            record(self.suite, self.pending, self.book)
        self.assertTrue(self.pending.exists())
        self.assertEqual(self.book.read_bytes(), before)

    def test_retries_when_workbook_is_locked(self):
        self.write_pending("NET-001", "PASS", "Ann", "")
        real = results_mod.write_workbook
        calls = {"n": 0}

        def flaky(*a, **kw):
            calls["n"] += 1
            if calls["n"] < 3:
                raise PermissionError("locked by Excel")
            return real(*a, **kw)

        sleeps = []
        with mock.patch.object(results_mod, "write_workbook", flaky):
            record(self.suite, self.pending, self.book, sleep=sleeps.append, delay=0.5)
        self.assertEqual((calls["n"], sleeps), (3, [0.5, 0.5]))
        self.assertFalse(self.pending.exists())

    def test_gives_up_but_keeps_pending_result(self):
        self.write_pending("NET-001", "PASS", "Ann", "")
        with mock.patch.object(results_mod, "write_workbook", side_effect=PermissionError("locked")):
            with self.assertRaises(PermissionError) as ctx:
                record(self.suite, self.pending, self.book, sleep=lambda s: None)
        self.assertIn("close it in Excel", str(ctx.exception))
        self.assertTrue(self.pending.exists())

    def test_success_clears_stale_error_log(self):
        log_error(self.book, RuntimeError("old failure"))
        self.assertTrue((self.dir / "qa_runner_error.log").exists())
        self.write_pending("NET-001", "PASS", "Ann", "")
        record(self.suite, self.pending, self.book)
        self.assertFalse((self.dir / "qa_runner_error.log").exists())

    def test_error_log_appends_with_traceback(self):
        for msg in ("first", "second"):
            try:
                raise ValueError(msg)
            except ValueError as exc:
                log = log_error(self.book, exc)
        text = log.read_text(encoding="utf-8")
        self.assertIn("ValueError: first", text)
        self.assertIn("ValueError: second", text)
        self.assertIn("Traceback", text)


if __name__ == "__main__":
    unittest.main()

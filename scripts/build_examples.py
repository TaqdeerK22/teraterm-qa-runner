#!/usr/bin/env python3
"""Rebuild everything in examples/ from suites/demo_suite.json.

    python scripts/build_examples.py           # rewrite the example files
    python scripts/build_examples.py --check   # exit 1 if they are out of date (used by CI)

Text files are compared byte for byte. The .xlsx is compared by the contents of
its zip members, because zip bytes can differ between platforms and zlib builds.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from qa_runner.model import Result  # noqa: E402
from qa_runner.report import render_html, render_markdown, summarize  # noqa: E402
from qa_runner.suite import load_suite  # noqa: E402
from qa_runner.ttl import MacroOptions, generate_macro  # noqa: E402
from qa_runner.xlsx import write_workbook  # noqa: E402

STAMP = "2026-01-15T14:30:00Z"
SAMPLE = {
    "BOOT-001": ("PASS", "Firmware 2.4.1, build 2025-11-02"),
    "BOOT-002": ("PASS", ""),
    "BOOT-003": ("PASS", ""),
    "NET-001": ("PASS", "Leased 192.0.2.57"),
    "NET-002": ("FAIL", "Link LED went off for ~8 s after net apply"),
    "NET-003": ("BLOCKED", "No workstation available on the bench network"),
    "LED-001": ("PASS", ""),
    "LED-002": ("SKIP", "Needs the optical rig - scheduled for next week"),
}


def build(out: Path) -> None:
    suite = load_suite(ROOT / "suites" / "demo_suite.json")
    out.mkdir(parents=True, exist_ok=True)
    macro = generate_macro(suite, MacroOptions(suite_rel_path="..\\suites\\demo_suite.json"))
    with open(out / "demo_suite.ttl", "w", encoding="ascii", newline="\n") as fh:
        fh.write(macro)

    results = {tid: Result(status, comment, "Alex Example", STAMP)
               for tid, (status, comment) in SAMPLE.items()}
    write_workbook(out / "demo_results.xlsx", suite, results, STAMP)
    summary = summarize(suite, results)
    with open(out / "demo_report.md", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render_markdown(summary))
    with open(out / "demo_report.html", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render_html(summary, results))


def _zip_members(path: Path) -> dict:
    with zipfile.ZipFile(path) as z:
        return {name: z.read(name) for name in z.namelist()}


def _same(actual: Path, fresh: Path) -> bool:
    if not actual.exists():
        return False
    if fresh.suffix == ".xlsx":
        return _zip_members(actual) == _zip_members(fresh)
    return actual.read_bytes() == fresh.read_bytes()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="verify instead of writing")
    args = parser.parse_args()
    target = ROOT / "examples"
    if not args.check:
        build(target)
        print("examples/ rebuilt")
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        fresh = Path(tmp)
        build(fresh)
        stale = [p.name for p in sorted(fresh.iterdir()) if not _same(target / p.name, p)]
    if stale:
        print("examples/ is out of date: " + ", ".join(stale), file=sys.stderr)
        print("run: python scripts/build_examples.py", file=sys.stderr)
        return 1
    print("examples/ is up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
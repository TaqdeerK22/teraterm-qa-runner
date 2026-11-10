"""Command-line interface: ``python -m qa_runner <command>`` (or ``qa-runner``)."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__
from .model import STATUS_NAMES, Result, normalize_status
from .report import render_csv, render_html, render_markdown, render_text, summarize
from .results import PendingError, log_error, record, utc_now
from .suite import SuiteError, load_suite, select_tests
from .ttl import MacroOptions, generate_macro, lint
from .xlsx import read_results, write_workbook

EXIT_OK, EXIT_FAIL, EXIT_USAGE = 0, 1, 2


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="qa-runner", description=__doc__.splitlines()[0])
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True, metavar="command")

    v = sub.add_parser("validate", help="check a suite file and report every problem")
    v.add_argument("suite")

    g = sub.add_parser("generate", help="generate the Tera Term macro for a suite")
    g.add_argument("suite")
    g.add_argument("-o", "--output", required=True, help="macro file to write (.ttl)")
    g.add_argument("--python", default="py -3", dest="python_cmd",
                   help="command the macro uses to start Python (default: 'py -3')")
    g.add_argument("--results-dir-name", default="qa_results",
                   help="folder created under %%USERPROFILE%% (default: qa_results)")
    g.add_argument("--ids", nargs="+", metavar="ID", help="only these tests")
    g.add_argument("--group", help="only tests in this group")
    g.add_argument("--from", dest="start_at", metavar="ID", help="start at this test")
    g.add_argument("--results", metavar="XLSX",
                   help="existing results workbook (used with --only-status)")
    g.add_argument("--only-status", metavar="LIST",
                   help="with --results: only tests whose status is in this comma list, "
                        "e.g. 'FAIL,NOT_RUN' (re-run what is left or broken)")

    i = sub.add_parser("init", help="create an empty results workbook (all NOT RUN)")
    i.add_argument("suite")
    i.add_argument("workbook")
    i.add_argument("--force", action="store_true", help="overwrite an existing workbook")

    r = sub.add_parser("record", help="(used by the macro) save one pending result")
    r.add_argument("suite")
    r.add_argument("pending")
    r.add_argument("workbook")

    rp = sub.add_parser("report", help="summarize a results workbook")
    rp.add_argument("suite")
    rp.add_argument("workbook")
    rp.add_argument("--format", choices=("text", "md", "html", "csv"), default="text")
    rp.add_argument("-o", "--output", help="write to a file instead of stdout")
    rp.add_argument("--fail-on-fail", action="store_true",
                    help="exit with status 1 if any test is FAIL (for CI use)")
    return p


def _relative_suite_path(suite: Path, out_dir: Path) -> str:
    """Suite path relative to the macro folder, with Windows separators."""
    try:
        rel = os.path.relpath(suite.resolve(), out_dir.resolve())
    except ValueError:                     # different drives on Windows
        rel = str(suite.resolve())
    return rel.replace("/", "\\")


def _cmd_validate(args: argparse.Namespace) -> int:
    suite = load_suite(args.suite)
    steps = sum(len(t.steps) for t in suite.tests)
    print(f"OK: {suite.name} v{suite.version} - {len(suite.tests)} tests in "
          f"{len(suite.groups())} groups, {steps} steps")
    return EXIT_OK


def _cmd_generate(args: argparse.Namespace) -> int:
    suite = load_suite(args.suite)
    ids = args.ids
    if args.only_status:
        if not args.results:
            raise SuiteError(["--only-status needs --results"])
        wanted = set()
        for item in args.only_status.split(","):
            status = normalize_status(item)
            if status is None:
                raise SuiteError([f"unknown status '{item.strip()}' (use {', '.join(STATUS_NAMES)})"])
            wanted.add(status)
        results = read_results(args.results)
        by_status = [t.id for t in suite.tests
                     if results.get(t.id, Result()).status in wanted]
        ids = by_status if ids is None else [i for i in ids if i in set(by_status)]
    tests = select_tests(suite, ids=ids, group=args.group, start_at=args.start_at)
    out = Path(args.output)
    options = MacroOptions(
        suite_rel_path=_relative_suite_path(Path(args.suite), out.parent),
        results_dir_name=args.results_dir_name, python_cmd=args.python_cmd, tests=tests)
    macro = generate_macro(suite, options)
    problems = lint(macro)
    if problems:                            # a bug in the generator, never user error
        raise RuntimeError("generated macro failed lint:\n  " + "\n  ".join(problems))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(macro, encoding="ascii", newline="\n")
    print(f"wrote {out} ({len(tests)} of {len(suite.tests)} tests)")
    return EXIT_OK


def _cmd_init(args: argparse.Namespace) -> int:
    suite = load_suite(args.suite)
    book = Path(args.workbook)
    if book.exists() and not args.force:
        print(f"error: {book} exists (use --force to overwrite)", file=sys.stderr)
        return EXIT_USAGE
    write_workbook(book, suite, {}, utc_now())
    print(f"wrote {book}")
    return EXIT_OK


def _cmd_record(args: argparse.Namespace) -> int:
    suite = load_suite(args.suite)
    try:
        pending = record(suite, args.pending, args.workbook)
    except Exception as exc:                 # noqa: BLE001 - logged, then reported by exit code
        log = log_error(args.workbook, exc)
        print(f"error: {exc} (details in {log})", file=sys.stderr)
        return EXIT_FAIL
    print(f"saved {pending.test_id} = {pending.status}")
    return EXIT_OK


def _cmd_report(args: argparse.Namespace) -> int:
    suite = load_suite(args.suite)
    results = read_results(args.workbook)
    summary = summarize(suite, results)
    text = {"text": lambda: render_text(summary),
            "md": lambda: render_markdown(summary),
            "html": lambda: render_html(summary, results),
            "csv": lambda: render_csv(suite, results)}[args.format]()
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {args.output}")
    else:
        sys.stdout.write(text)
    return EXIT_FAIL if args.fail_on_fail and summary.counts["FAIL"] else EXIT_OK


_COMMANDS = {"validate": _cmd_validate, "generate": _cmd_generate, "init": _cmd_init,
             "record": _cmd_record, "report": _cmd_report}


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        return _COMMANDS[args.command](args)
    except SuiteError as exc:
        print(f"invalid suite ({len(exc.errors)} problem{'s' * (len(exc.errors) != 1)}):",
              file=sys.stderr)
        for line in exc.errors:
            print(f"  - {line}", file=sys.stderr)
        return EXIT_USAGE
    except (PendingError, FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE

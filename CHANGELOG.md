# Changelog

All notable changes are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and the project uses
[Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-01-15

First public release.

### Added
- JSON test suites with validation that reports every problem at once.
- Tera Term macro generator: one shared `qa_record` subroutine, any number of tests.
- Results workbook: colour-coded statuses, status dropdown, frozen header, print setup,
  and a **Summary** sheet with live formulas (counts, progress, pass rate, per-group table).
- Tester name and UTC timestamp recorded with every result.
- `send_secret` steps: passwords are typed into a masked box and never written to disk.
- Partial and repeat runs: `--ids`, `--group`, `--from`, and `--results --only-status`.
- Reports as text, Markdown, HTML and CSV; `--fail-on-fail` for CI.
- Tolerant workbook reader (understands files re-saved by Excel).
- Atomic workbook writes with retry when Excel holds the file.
- Structural macro linter, run on every generated macro.
- 86 unit tests; CI on Linux, Windows and macOS, Python 3.9-3.13.

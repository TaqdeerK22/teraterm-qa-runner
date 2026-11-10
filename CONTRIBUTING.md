# Contributing

Thanks for helping! The project is small and standard-library only, so setup is short.

```bash
git clone https://github.com/OWNER/teraterm-qa-runner
cd teraterm-qa-runner
python -m pip install -e .
python -m unittest discover -s tests -v      # or: python -m pytest
python scripts/build_examples.py --check
```

## Ground rules
- **No runtime dependencies.** Anything beyond the standard library needs a strong reason.
- Add or update tests for every behaviour change. The test suite must stay green on Windows,
  macOS and Linux (CI checks this).
- If you change the generator, the workbook layout or reports, run
  `python scripts/build_examples.py` and commit the refreshed `examples/` files - CI fails when
  they are stale.
- Changes to the generated macro must be **verified in a real Tera Term** (the unit tests can
  only check its structure). Follow [docs/TESTING_THE_MACRO.md](docs/TESTING_THE_MACRO.md) and
  mention the Tera Term version you used in the pull request.

## Where things live
See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Common extensions:
- **New status:** add it to `STATUSES` in `model.py` (name, key, colours). The macro prompt,
  matching, workbook colours/dropdown and reports all follow automatically.
- **New step type:** parse it in `suite.py`, emit it in `_emit_steps` in `ttl.py`, document it in
  `docs/SUITE_FORMAT.md`, add tests.
- **New report format:** add a renderer in `report.py` and a choice in `cli.py`.

## Style
Readable over clever; type hints on public functions; short docstrings that say *why*.

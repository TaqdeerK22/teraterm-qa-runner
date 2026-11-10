# Architecture

## Goals
1. Never lose a result.
2. Tests are data, not code: reviewable, diffable, and validated before anyone sits at a device.
3. Run on a locked-down PC: Python plus Tera Term, nothing to install from the internet.

## Components

```
suite.json --load/validate--> Suite --generate--> macro.ttl            (build time)

macro.ttl --(per test)--> pending file --record--> results.xlsx        (run time)
                                                         |
                                            report --> text / md / html / csv
```

| Module | Responsibility |
|---|---|
| `model.py` | `Status` table and `Result`. Every other module derives from it: the macro prompt, the status matching, the Excel colours and dropdown, the reports. Add a status here and it appears everywhere |
| `suite.py` | Parse and validate; collect all errors; select tests for partial runs |
| `ttl.py` | Emit the macro; `quote()` implements TTL string quoting; `lint()` is a structural checker |
| `xlsx.py` | Write/read the workbook |
| `results.py` | Parse the pending file, merge, retry, error log |
| `report.py` | Summaries |
| `cli.py` | Argument parsing and exit codes (0 ok, 1 runtime failure, 2 bad input) |

## The generated macro

Straight-line steps per test, then one call:

```
sendln 'net show'
pause 2
messagebox 'Verify ...' 'NET-001: Default network settings'
qa_id = 'NET-001'
call qa_record
```

TTL has no functions with parameters, so subroutines communicate through **global variables**:
`qa_record` reads `qa_id`, `qa_tester`, `qa_pending`, `qa_savecmd` and `qa_dir`. `qa_match` is
a helper called once per status with `qa_short` / `qa_full` set. The main program ends with `end`
**before** the subroutines; without it execution would fall into `qa_record`.

`qa_record` in order: build titles -> ask status (uppercase once, compare with each short/full form,
loop on invalid, offer to stop on empty) -> ask comment -> write the pending file -> run Python and
wait -> check that the pending file is gone.

### Why `qa_match` is called five times instead of using `or`
TTL operator precedence is easy to get wrong, so each comparison is its own `if`. The status
list is data (`STATUSES`), so the generator emits one three-line group per status.

## The pending file (the contract between macro and Python)

Four-plus lines, written in the Windows ANSI code page by Tera Term:

```
NET-001          <- test id (must exist in the suite)
FAIL             <- status (canonical name; Python re-validates)
Alex Example     <- tester
Link LED stayed  <- comment: line 4 to end of file, may be empty
off
```

Why a file and not command-line arguments? Comments can contain quotes, `&`, `%` and accents; quoting
those through `cmd /c` is fragile. The file also doubles as a **transaction marker**: Python deletes
it only after a successful save, so "still exists" means "not saved".

`results.decode_text()` tries UTF-8 (with BOM), the Windows ANSI code page (`mbcs`), then cp1252.

## The workbook

Two sheets, written by hand as OOXML parts (`xl/worksheets/sheet1.xml` etc.):

- **Results** - one row per suite test, in suite order. Status colours are conditional formatting
  (`dxf` styles generated from `STATUSES`), the status column has a list validation, the header is
  frozen and filterable, and printing is landscape fit-to-width.
- **Summary** - metadata plus `COUNTIF` / `COUNTIFS` formulas. `fullCalcOnLoad` makes Excel compute
  them on open, so no cached values need to be written.

Design points:
- **Inline strings** (`t="inlineStr"`) avoid writing a shared-string table; Excel converts on next save.
- **Whole-file rewrite, atomic replace.** Each save reads the existing results, replaces one entry,
  writes a temp file in the same folder and `os.replace`s it over the workbook. A crash cannot
  corrupt it; on Windows `PermissionError` means Excel has it open, which triggers a short retry.
- **Tolerant reader.** `read_results()` finds the sheet by name through the workbook relationships and
  understands shared strings, sparse rows and rich text, so a workbook that a human re-saved in
  Excel still round-trips.
- **Reproducible output.** Fixed zip timestamps and deterministic XML let CI compare `examples/` byte for byte.
- XML-illegal control characters are stripped and cells are capped at Excel's 32,767-character limit.

## Failure modes

| Situation | Behaviour |
|---|---|
| Python missing / package not installed | Pending file remains -> macro shows "Saving X failed" and stops |
| Workbook open in Excel | 3 retries, then a clear error; pending file kept for manual `qa-runner record` |
| Bad status or unknown id in pending file | Error logged to `qa_runner_error.log`, workbook untouched, pending file kept |
| Empty status at the prompt | Offer to stop the run; saved results are kept |

## Extending
See CONTRIBUTING.md ("Where things live").

# Verifying the generated macro in Tera Term

The unit tests prove the macro is structurally sound (the linter checks `if`/`endif`, labels,
quoting and the `qa_id` + `call qa_record` pairing) but they cannot run TTL. Do this once per Tera Term
version you care about, and again whenever the macro generator changes.

## Setup
1. `py -3 -m pip install -e .`
2. `py -3 -m qa_runner generate suites\demo_suite.json -o macros\demo_suite.ttl --ids BOOT-001 NET-001`
3. Open Tera Term (a serial loopback or any session is enough - commands just need somewhere to go).
4. Remove any old `%USERPROFILE%\qa_results\widget-demo_results.xlsx`.

## Checklist (Control > Macro...)

| # | Action | Expected |
|---|---|---|
| 1 | Start the macro | Tester prompt, then "Start" message |
| 2 | Enter a password in the masked box | Characters hidden; nothing about it appears in the macro file |
| 3 | At the status prompt type `p` | Comment prompt appears |
| 4 | Add a comment containing `"quotes"`, `&`, `%` and an accented letter | Accepted |
| 5 | Next test: type `xyz` | "Invalid status" message, prompt again |
| 6 | Same prompt: leave empty, press OK | "Stop the run?" - answer **No** -> prompt again |
| 7 | Same prompt: type `FAIL` | Accepted |
| 8 | After the last test | "Done" message with the workbook path |
| 9 | Open the workbook | 2 results with correct status, comment text, tester and UTC time; Summary sheet shows the counts |
| 10 | Re-run, empty status, answer **Yes** | Macro stops; earlier results still in the workbook |
| 11 | Open the workbook in Excel, start the macro, record a result | Retry then an error naming `qa_runner_error.log`; the macro stops; close Excel and run `py -3 -m qa_runner record ...` by hand with the kept pending file |
| 12 | Temporarily rename the `qa_runner` folder / use a Python without the package | "Saving X failed" and the macro stops |

## Commands whose behaviour depends on the Tera Term version
`toupper`, `filesearch`, `yesnobox`, `passwordbox`, `foldersearch`, `foldercreate`, `getdir` and
the `result` value each returns. If one differs on your version, note the version and the observed
behaviour in an issue.

## Record the result
Edit the "Verification status" table in the README with the Tera Term version(s) and date.

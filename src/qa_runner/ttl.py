"""Generate a Tera Term macro (.ttl) from a Suite, and lint generated macros.

The generated macro is deliberately boring: straight-line instruction/command
steps for every test, each ending with ``call qa_record``. All of the logic
(asking for a result, validating it, saving it) lives in one subroutine.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence

from . import __version__
from .model import STATUSES
from .suite import Step, Suite, Test

ERROR_LOG_NAME = "qa_runner_error.log"
PENDING_NAME = "_pending_result.txt"


@dataclass
class MacroOptions:
    suite_rel_path: str                 # suite file, relative to the macro's folder
    results_dir_name: str = "qa_results"  # created under %USERPROFILE%
    python_cmd: str = "py -3"
    tests: Optional[Sequence[Test]] = None   # None = all tests in the suite


# --------------------------------------------------------------------------- #
# Quoting
# --------------------------------------------------------------------------- #
def quote(text: str) -> str:
    """Return ``text`` as a TTL string expression.

    TTL strings use single quotes and have no escape sequence, so a literal
    single quote is spliced in as the character code ``#39``.
    """
    parts: List[str] = []
    buf: List[str] = []
    for ch in text:
        if ch == "'":
            if buf:
                parts.append("'" + "".join(buf) + "'")
                buf = []
            parts.append("#39")
        elif 32 <= ord(ch) < 127:
            buf.append(ch)
        else:
            raise ValueError(f"character {ch!r} cannot be used in macro text")
    if buf:
        parts.append("'" + "".join(buf) + "'")
    return "".join(parts) or "''"


def _short(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


# --------------------------------------------------------------------------- #
# Step emission
# --------------------------------------------------------------------------- #
def _emit_steps(steps: Sequence[Step], title: str) -> List[str]:
    out: List[str] = []
    for step in steps:
        if step.kind == "instruct":
            out.append(f"messagebox {quote(step.text)} {quote(title)}")
        elif step.kind == "send":
            out.append(f"sendln {quote(step.text)}")
            if step.seconds:
                out.append(f"pause {step.seconds}")
        elif step.kind == "wait":
            out.append(f"pause {step.seconds}")
        elif step.kind == "send_secret":
            before, after = step.text.split("{secret}")
            fmt = _secret_format(before, after)
            out.append(f"passwordbox {quote(step.prompt)} {quote(title)}")
            out.append(f"sprintf2 qa_cmd {fmt} inputstr")
            out.append("sendln qa_cmd")
            out.append("qa_cmd = ''")
            if step.seconds:
                out.append(f"pause {step.seconds}")
        else:  # pragma: no cover - guarded by suite validation
            raise ValueError(f"unknown step kind {step.kind}")
    return out


def _secret_format(before: str, after: str) -> str:
    """Quote ``<before>%s<after>`` as a sprintf2 format; the secret is never written to the file."""
    return quote(before.replace("%", "%%") + "%s" + after.replace("%", "%%"))


# --------------------------------------------------------------------------- #
# Macro generation
# --------------------------------------------------------------------------- #
def generate_macro(suite: Suite, options: MacroOptions) -> str:
    tests = list(options.tests) if options.tests is not None else list(suite.tests)
    n = len(tests)
    L: List[str] = []
    add = L.append

    add("; " + "=" * 76)
    add("; GENERATED FILE - do not edit by hand.")
    add(f"; Suite : {_short(suite.name, 60)} ({suite.id}) v{suite.version}")
    add(f"; Tests : {n} of {len(suite.tests)}")
    add(f"; Made by teraterm-qa-runner {__version__}. Edit the suite JSON, then regenerate.")
    add("; " + "=" * 76)
    add(f"settitle {quote(suite.name)}")
    add("")
    add("; ---- settings (override here if needed) " + "-" * 36)
    add(f"qa_results_name = {quote(options.results_dir_name)}")
    add(f"qa_python = {quote(options.python_cmd)}")
    add(f"qa_suite_rel = {quote(options.suite_rel_path)}")
    add(f"qa_suite_id = {quote(suite.id)}")
    add("")
    add("; ---- results folder and paths " + "-" * 46)
    add("getenv 'USERPROFILE' qa_home")
    add("strlen qa_home")
    add("if result = 0 then")
    add("    messagebox 'USERPROFILE is not set.' 'Setup error'")
    add("    end")
    add("endif")
    add("sprintf2 qa_dir '%s\\%s' qa_home qa_results_name")
    add("foldersearch qa_dir")
    add("if result = 0 then")
    add("    foldercreate qa_dir")
    add("    if result <> 0 then")
    add("        messagebox 'Cannot create the results folder.' 'Setup error'")
    add("        end")
    add("    endif")
    add("endif")
    add(f"sprintf2 qa_pending '%s\\{PENDING_NAME}' qa_dir")
    add("sprintf2 qa_book '%s\\%s_results.xlsx' qa_dir qa_suite_id")
    add("getdir qa_macrodir")
    add("sprintf2 qa_suite '%s\\%s' qa_macrodir qa_suite_rel")
    add("sprintf2 qa_savecmd 'cmd /c %s -m qa_runner record \"%s\" \"%s\" \"%s\"' "
        "qa_python qa_suite qa_pending qa_book")
    add("")
    add("; ---- who is running this? (saved with every result) " + "-" * 24)
    add("inputbox 'Your name (saved with every result)' 'Tester' ''")
    add("qa_tester = inputstr")
    add("strlen qa_tester")
    add("if result = 0 then")
    add("    qa_tester = 'unknown'")
    add("endif")
    add("")
    add(f"messagebox {quote(_short(f'{suite.name}: {n} tests. Ready?', 120))} 'Start'")
    add("")

    if suite.setup:
        add("; ---- setup " + "-" * 62)
        L.extend(_emit_steps(suite.setup, "Setup"))
        add("")

    for index, test in enumerate(tests, 1):
        title = f"{test.id} [{index}/{n}]"
        add("; " + "-" * 4 + f" {test.id}: {_short(test.title, 60)} " + "-" * 4)
        L.extend(_emit_steps(test.steps, title))
        add(f"messagebox {quote(test.verify)} {quote(_short(test.id + ': ' + test.title, 80))}")
        add(f"qa_id = {quote(test.id)}")
        add("call qa_record")
        add("")

    if suite.teardown:
        add("; ---- teardown " + "-" * 59)
        L.extend(_emit_steps(suite.teardown, "Teardown"))
        add("")

    add("sprintf2 qa_msg 'Run finished. Results are in:%s' qa_book")
    add("messagebox qa_msg 'Done'")
    add("end")
    add("")
    L.extend(_subroutines())
    return "\n".join(L) + "\n"


def _subroutines() -> List[str]:
    keys = ", ".join(f"{s.key}={s.name}" for s in STATUSES)
    prompt = quote(f"Enter {keys} (the full word also works)")
    invalid = quote("Invalid status. Use " + ", ".join(s.key for s in STATUSES)
                    + " or the full status name. Please try again.")
    L: List[str] = []
    add = L.append
    add(";" + "=" * 77)
    add("; qa_record - ask for a result and a comment, then save them to Excel.")
    add(";   IN : qa_id, qa_tester, qa_pending, qa_savecmd, qa_dir (globals)")
    add(";   OUT: the test's row is updated; the macro stops if the save fails.")
    add(";=" + "=" * 76)
    add(":qa_record")
    add("sprintf2 qa_title_status 'Result for %s' qa_id")
    add("sprintf2 qa_title_notes 'Comment for %s' qa_id")
    add("")
    add(":qa_ask_status")
    add(f"inputbox {prompt} qa_title_status ''")
    add("qa_raw = inputstr")
    add("toupper qa_key qa_raw")
    add("qa_status = ''")
    for s in STATUSES:
        add(f"qa_short = {quote(s.key)}")
        add(f"qa_full = {quote(s.name)}")
        add("call qa_match")
    add("strlen qa_status")
    add("if result > 0 then")
    add("    goto qa_status_ok")
    add("endif")
    add("")
    add("; Nothing valid: ask again. Empty input (or Cancel) offers a way out.")
    add("strlen qa_raw")
    add("if result = 0 then")
    add("    yesnobox 'No status entered. Stop the run? (saved results are kept)' 'No status'")
    add("    if result = 1 then")
    add("        end")
    add("    endif")
    add("else")
    add(f"    messagebox {invalid} 'Invalid status'")
    add("endif")
    add("goto qa_ask_status")
    add("")
    add(":qa_status_ok")
    add("inputbox 'Comment / what you observed (optional)' qa_title_notes ''")
    add("qa_notes = inputstr")
    add("")
    add("; Hand over to Python through the pending file (id, status, tester, comment).")
    add("filecreate qa_fh qa_pending")
    add("if qa_fh = -1 then")
    add("    messagebox 'Cannot create the pending result file.' 'Save error'")
    add("    end")
    add("endif")
    add("filewriteln qa_fh qa_id")
    add("filewriteln qa_fh qa_status")
    add("filewriteln qa_fh qa_tester")
    add("filewriteln qa_fh qa_notes")
    add("fileclose qa_fh")
    add("exec qa_savecmd 'hide' 1")
    add("")
    add("; Python deletes the pending file after a successful save. Still there = failed.")
    add("filesearch qa_pending")
    add("if result <> 0 then")
    add(f"    sprintf2 qa_msg 'Saving %s failed. See {ERROR_LOG_NAME} in:%s' qa_id qa_dir")
    add("    messagebox qa_msg 'Save error'")
    add("    end")
    add("endif")
    add("return")
    add("")
    add(";" + "-" * 77)
    add("; qa_match - if qa_key equals qa_short or qa_full, set qa_status to qa_full.")
    add(";" + "-" * 77)
    add(":qa_match")
    add("strcompare qa_key qa_short")
    add("if result = 0 then")
    add("    qa_status = qa_full")
    add("endif")
    add("strcompare qa_key qa_full")
    add("if result = 0 then")
    add("    qa_status = qa_full")
    add("endif")
    add("return")
    return L


# --------------------------------------------------------------------------- #
# Lint
# --------------------------------------------------------------------------- #
_LABEL = re.compile(r"^:([A-Za-z_][A-Za-z0-9_]*)\s*$")
_JUMP = re.compile(r"^(goto|call)\s+([A-Za-z_][A-Za-z0-9_]*)\s*$")


def lint(macro: str) -> List[str]:
    """Structural checks on a generated macro. Returns a list of problems (empty = clean)."""
    problems: List[str] = []
    labels: dict = {}
    ifs = endifs = 0
    for no, line in enumerate(macro.splitlines(), 1):
        stripped = line.strip()
        if len(line) > 500:
            problems.append(f"line {no}: longer than 500 characters")
        if stripped.count("'") % 2 and "#39" not in stripped and not stripped.startswith(";"):
            problems.append(f"line {no}: unbalanced single quote")
        m = _LABEL.match(stripped)
        if m:
            if m.group(1) in labels:
                problems.append(f"line {no}: duplicate label {m.group(1)}")
            labels[m.group(1)] = no
        if re.match(r"^if\b.*\bthen$", stripped):
            ifs += 1
        elif stripped == "endif":
            endifs += 1
    if ifs != endifs:
        problems.append(f"if/endif mismatch: {ifs} if, {endifs} endif")
    previous = ""
    for no, line in enumerate(macro.splitlines(), 1):
        stripped = line.strip()
        m = _JUMP.match(stripped)
        if m and m.group(2) not in labels:
            problems.append(f"line {no}: {m.group(1)} to undefined label {m.group(2)}")
        if stripped == "call qa_record" and not previous.startswith("qa_id = "):
            problems.append(f"line {no}: 'call qa_record' must follow 'qa_id = ...'")
        if stripped:
            previous = stripped
    if "end" not in [ln.strip() for ln in macro.splitlines()]:
        problems.append("no 'end' before the subroutines")
    return problems

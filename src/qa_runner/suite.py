"""Loading and validating test suites (JSON).

A suite is a plain JSON document; see docs/SUITE_FORMAT.md. All problems found
are collected and reported together so authors fix them in one pass.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = 1
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,31}$")
MAX_TEXT = 250          # keeps every generated macro string comfortably short
MAX_WAIT_S = 3600
DEFAULT_GROUP = "General"
DEFAULT_WAIT_S = 2


class SuiteError(ValueError):
    """Raised when a suite is invalid; ``errors`` lists every problem."""

    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


@dataclass(frozen=True)
class Step:
    kind: str                 # instruct | send | send_secret | wait
    text: str = ""            # instruction text, command, or secret command template
    seconds: int = 0          # pause after a command / duration of a wait
    prompt: str = ""          # send_secret: label of the password box


@dataclass(frozen=True)
class Test:
    id: str
    title: str
    group: str
    steps: List[Step]
    verify: str


@dataclass(frozen=True)
class Suite:
    id: str
    name: str
    version: str
    description: str
    setup: List[Step] = field(default_factory=list)
    tests: List[Test] = field(default_factory=list)
    teardown: List[Step] = field(default_factory=list)

    def test_ids(self) -> List[str]:
        return [t.id for t in self.tests]

    def groups(self) -> List[str]:
        seen: List[str] = []
        for t in self.tests:
            if t.group not in seen:
                seen.append(t.group)
        return seen


# --------------------------------------------------------------------------- #
def load_suite(path: "str | Path") -> Suite:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise SuiteError([f"not valid JSON: {exc}"]) from exc
    return parse_suite(raw)


def _macro_text(value: Any, where: str, errors: List[str], *, required: bool = True) -> str:
    """Validate a string that will end up inside the generated macro."""
    if not isinstance(value, str) or (required and not value.strip()):
        errors.append(f"{where}: must be a non-empty string")
        return ""
    if len(value) > MAX_TEXT:
        errors.append(f"{where}: longer than {MAX_TEXT} characters")
    if not all(32 <= ord(c) < 127 for c in value):
        errors.append(f"{where}: only printable ASCII is supported in macro text")
    return value


def _parse_steps(raw: Any, where: str, default_wait: int, errors: List[str]) -> List[Step]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        errors.append(f"{where}: must be a list of steps")
        return []
    steps: List[Step] = []
    for i, item in enumerate(raw, 1):
        loc = f"{where}[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{loc}: a step must be an object")
            continue
        kinds = [k for k in ("instruct", "send", "send_secret", "wait") if k in item]
        if len(kinds) != 1:
            errors.append(f"{loc}: needs exactly one of instruct/send/send_secret/wait")
            continue
        kind = kinds[0]
        allowed = {kind} | ({"wait_after"} if kind in ("send", "send_secret") else set())
        if kind == "send_secret":
            allowed |= {"prompt"}
        for extra in sorted(set(item) - allowed):
            errors.append(f"{loc}: unknown key '{extra}' for a {kind} step")

        if kind == "wait":
            secs = item["wait"]
            if not _is_seconds(secs):
                errors.append(f"{loc}.wait: must be an integer 0-{MAX_WAIT_S}")
                continue
            steps.append(Step("wait", seconds=secs))
            continue

        text = _macro_text(item[kind], f"{loc}.{kind}", errors)
        secs = item.get("wait_after", default_wait) if kind != "instruct" else 0
        if not _is_seconds(secs):
            errors.append(f"{loc}.wait_after: must be an integer 0-{MAX_WAIT_S}")
            secs = 0
        if kind == "send_secret":
            if text.count("{secret}") != 1:
                errors.append(f"{loc}.send_secret: must contain '{{secret}}' exactly once")
            prompt = _macro_text(item.get("prompt", "Password"), f"{loc}.prompt", errors)
            steps.append(Step(kind, text, secs, prompt))
        else:
            steps.append(Step(kind, text, secs))
    return steps


def _is_seconds(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= MAX_WAIT_S


def parse_suite(raw: Any) -> Suite:
    errors: List[str] = []
    if not isinstance(raw, dict):
        raise SuiteError(["top level must be a JSON object"])
    if raw.get("schema", SCHEMA_VERSION) != SCHEMA_VERSION:
        errors.append(f"schema: unsupported version (this tool reads schema {SCHEMA_VERSION})")

    suite_id = raw.get("id", "")
    if not isinstance(suite_id, str) or not ID_PATTERN.match(suite_id):
        errors.append("id: required; letters, digits, '_', '.', '-' (max 32 characters)")
    name = _macro_text(raw.get("name"), "name", errors)
    version = str(raw.get("version", "1"))
    description = raw.get("description", "")
    if not isinstance(description, str):
        errors.append("description: must be a string")
        description = ""

    default_wait = raw.get("default_wait", DEFAULT_WAIT_S)
    if not _is_seconds(default_wait):
        errors.append(f"default_wait: must be an integer 0-{MAX_WAIT_S}")
        default_wait = DEFAULT_WAIT_S

    setup = _parse_steps(raw.get("setup"), "setup", default_wait, errors)
    teardown = _parse_steps(raw.get("teardown"), "teardown", default_wait, errors)

    tests: List[Test] = []
    seen: Dict[str, int] = {}
    raw_tests = raw.get("tests")
    if not isinstance(raw_tests, list) or not raw_tests:
        errors.append("tests: required, a non-empty list")
        raw_tests = []
    for i, item in enumerate(raw_tests, 1):
        loc = f"tests[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{loc}: must be an object")
            continue
        tid = item.get("id", "")
        if not isinstance(tid, str) or not ID_PATTERN.match(tid):
            errors.append(f"{loc}.id: required; letters, digits, '_', '.', '-' (max 32 characters)")
            tid = f"#{i}"
        elif tid in seen:
            errors.append(f"{loc}.id: duplicate of tests[{seen[tid]}] ('{tid}')")
        else:
            seen[tid] = i
        loc = f"test {tid}"
        title = _macro_text(item.get("title"), f"{loc}.title", errors)
        group = item.get("group", DEFAULT_GROUP)
        if not isinstance(group, str) or not group.strip():
            errors.append(f"{loc}.group: must be a non-empty string")
            group = DEFAULT_GROUP
        steps = _parse_steps(item.get("steps"), f"{loc}.steps", default_wait, errors)
        verify = _macro_text(item.get("verify"), f"{loc}.verify", errors)
        tests.append(Test(tid, title, group.strip(), steps, verify))

    if errors:
        raise SuiteError(errors)
    return Suite(suite_id, name, version, description, setup, tests, teardown)


def select_tests(suite: Suite, ids: Optional[List[str]] = None, group: Optional[str] = None,
                 start_at: Optional[str] = None) -> List[Test]:
    """Filter tests (used by the generator for partial / re-runs). Order is preserved."""
    tests = list(suite.tests)
    if ids is not None:
        unknown = sorted(set(ids) - set(suite.test_ids()))
        if unknown:
            raise SuiteError([f"unknown test id(s): {', '.join(unknown)}"])
        tests = [t for t in tests if t.id in set(ids)]
    if group is not None:
        if group not in suite.groups():
            raise SuiteError([f"unknown group '{group}' (have: {', '.join(suite.groups())})"])
        tests = [t for t in tests if t.group == group]
    if start_at is not None:
        if start_at not in suite.test_ids():
            raise SuiteError([f"unknown test id for --from: {start_at}"])
        index = [t.id for t in tests].index(start_at) if start_at in [t.id for t in tests] else None
        if index is None:
            raise SuiteError([f"--from {start_at} is not in the selected tests"])
        tests = tests[index:]
    if not tests:
        raise SuiteError(["the selection contains no tests"])
    return tests

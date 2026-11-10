"""Turning the macro's pending-result file into a row in the workbook."""
from __future__ import annotations

import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from .model import Result, normalize_status
from .suite import Suite
from .xlsx import read_results, write_workbook

ERROR_LOG_NAME = "qa_runner_error.log"
MAX_TESTER = 100


class PendingError(ValueError):
    """The pending file is missing, incomplete or refers to an unknown test."""


@dataclass(frozen=True)
class Pending:
    test_id: str
    status: str
    tester: str
    comment: str


def decode_text(raw: bytes) -> str:
    """Decode text written by Tera Term, which uses the Windows ANSI code page, not UTF-8."""
    for encoding in ("utf-8-sig", "mbcs", "cp1252"):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def parse_pending(raw: bytes, suite: Suite) -> Pending:
    """Parse and validate the 4-line hand-off file: id, status, tester, comment (rest)."""
    lines = decode_text(raw).splitlines()
    if len(lines) < 3:
        raise PendingError("pending file is incomplete (expected id, status, tester, comment)")
    test_id = lines[0].strip()
    if test_id not in suite.test_ids():
        raise PendingError(f"unknown test id '{test_id}'")
    status = normalize_status(lines[1])
    if status is None:
        raise PendingError(f"invalid status '{lines[1].strip()}'")
    tester = lines[2].strip()[:MAX_TESTER]
    comment = "\n".join(lines[3:]).rstrip()
    return Pending(test_id, status, tester, comment)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record(suite: Suite, pending_path: "str | Path", book_path: "str | Path", *,
           now: Optional[str] = None, retries: int = 3, delay: float = 1.0,
           sleep: Callable[[float], None] = time.sleep) -> Pending:
    """Merge the pending result into the workbook, then delete the pending file.

    The pending file is removed only after a successful save - the macro treats
    "file still exists" as "save failed". Retries cover the short time Excel or
    an antivirus scanner may hold the workbook.
    """
    pending_path, book_path = Path(pending_path), Path(book_path)
    pending = parse_pending(pending_path.read_bytes(), suite)
    stamp = now or utc_now()
    for attempt in range(1, retries + 1):
        try:
            results = read_results(book_path)
            results[pending.test_id] = Result(pending.status, pending.comment,
                                              pending.tester, stamp)
            write_workbook(book_path, suite, results, stamp)
            break
        except PermissionError as exc:
            if attempt == retries:
                raise PermissionError(
                    f"cannot write {book_path} - close it in Excel and retry. "
                    "The pending result was kept.") from exc
            sleep(delay)
    pending_path.unlink()
    (book_path.parent / ERROR_LOG_NAME).unlink(missing_ok=True)
    return pending


def log_error(book_path: "str | Path", exc: BaseException) -> Path:
    """Append a timestamped error (with traceback) next to the workbook."""
    log = Path(book_path).parent / ERROR_LOG_NAME
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as fh:
        fh.write(f"[{utc_now()}] {type(exc).__name__}: {exc}\n")
        fh.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)) + "\n")
    return log

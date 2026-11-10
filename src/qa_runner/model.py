"""Core data model: test statuses and recorded results.

Everything that needs to know the list of statuses (macro generator, workbook
writer, reports, validation) reads it from here, so a status is added in
exactly one place.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Status:
    name: str            # canonical, upper case, stored in the workbook
    key: str             # single letter accepted at the macro prompt
    font_color: Optional[str] = None   # ARGB, used for conditional formatting
    fill_color: Optional[str] = None


STATUSES = (
    Status("PASS", "P", "FF006100", "FFC6EFCE"),
    Status("FAIL", "F", "FF9C0006", "FFFFC7CE"),
    Status("BLOCKED", "B", "FF9C5700", "FFFFEB9C"),
    Status("SKIP", "S", "FF595959", "FFEDEDED"),
    Status("NOT RUN", "N"),
)
STATUS_NAMES = tuple(s.name for s in STATUSES)
DEFAULT_STATUS = "NOT RUN"


def normalize_status(text: str) -> Optional[str]:
    """Return the canonical status for user input, or None if it is not valid.

    Accepts the letter (``p``), the name (``pass``) and, for command-line use,
    underscores or extra spaces (``not_run``, ``NOT  RUN``). Case-insensitive.
    """
    cleaned = " ".join(text.replace("_", " ").split()).upper()
    for status in STATUSES:
        if cleaned in (status.key, status.name):
            return status.name
    return None


@dataclass(frozen=True)
class Result:
    """One recorded outcome for one test."""

    status: str = DEFAULT_STATUS
    comment: str = ""
    tester: str = ""
    recorded_at: str = ""   # ISO-8601 UTC, e.g. 2026-01-31T14:05:09Z

"""Summaries of a run in text, Markdown, HTML and CSV."""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from html import escape
from typing import Dict, List, Mapping, Optional, Tuple

from .model import DEFAULT_STATUS, STATUS_NAMES, Result
from .suite import Suite, Test

ATTENTION = ("FAIL", "BLOCKED")


@dataclass(frozen=True)
class Summary:
    suite: Suite
    counts: Dict[str, int]
    by_group: List[Tuple[str, Dict[str, int]]]
    attention: List[Tuple[Test, Result]]

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    @property
    def executed(self) -> int:
        return self.total - self.counts[DEFAULT_STATUS]

    @property
    def progress(self) -> float:
        return self.executed / self.total if self.total else 0.0

    @property
    def pass_rate(self) -> Optional[float]:
        decided = self.counts["PASS"] + self.counts["FAIL"]
        return self.counts["PASS"] / decided if decided else None


def summarize(suite: Suite, results: Mapping[str, Result]) -> Summary:
    counts = {name: 0 for name in STATUS_NAMES}
    groups: Dict[str, Dict[str, int]] = {g: {n: 0 for n in STATUS_NAMES} for g in suite.groups()}
    attention: List[Tuple[Test, Result]] = []
    for test in suite.tests:
        result = results.get(test.id, Result())
        counts[result.status] += 1
        groups[test.group][result.status] += 1
        if result.status in ATTENTION:
            attention.append((test, result))
    return Summary(suite, counts, list(groups.items()), attention)


def _pct(value: Optional[float]) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


# --------------------------------------------------------------------------- #
def render_text(summary: Summary) -> str:
    s = summary
    out = [f"{s.suite.name} (v{s.suite.version})", "=" * 60]
    for name in STATUS_NAMES:
        out.append(f"{name:<10}{s.counts[name]:>5}")
    out += ["-" * 15, f"{'Total':<10}{s.total:>5}", "",
            f"Progress : {_pct(s.progress)} ({s.executed}/{s.total} executed)",
            f"Pass rate: {_pct(s.pass_rate)} (PASS / (PASS + FAIL))"]
    if s.attention:
        out += ["", "Needs attention:"]
        for test, r in s.attention:
            note = f" - {r.comment}" if r.comment else ""
            out.append(f"  [{r.status}] {test.id} {test.title}{note}")
    return "\n".join(out) + "\n"


def _md(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(summary: Summary) -> str:
    s = summary
    out = [f"# {s.suite.name}", "", f"Suite `{s.suite.id}` v{s.suite.version}", "",
           "| Status | Count |", "|---|---:|"]
    out += [f"| {n} | {s.counts[n]} |" for n in STATUS_NAMES]
    out += [f"| **Total** | **{s.total}** |", "",
            f"- Progress: **{_pct(s.progress)}** ({s.executed}/{s.total} executed)",
            f"- Pass rate: **{_pct(s.pass_rate)}** (PASS / (PASS + FAIL))", "",
            "## By group", "", "| Group | " + " | ".join(STATUS_NAMES) + " |",
            "|---|" + "---:|" * len(STATUS_NAMES)]
    for group, c in s.by_group:
        out.append(f"| {_md(group)} | " + " | ".join(str(c[n]) for n in STATUS_NAMES) + " |")
    if s.attention:
        out += ["", "## Needs attention", "", "| ID | Status | Test | Comment |", "|---|---|---|---|"]
        for test, r in s.attention:
            out.append(f"| {test.id} | {r.status} | {_md(test.title)} | {_md(r.comment)} |")
    return "\n".join(out) + "\n"


def render_csv(suite: Suite, results: Mapping[str, Result]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["ID", "Group", "Test", "Status", "Comment", "Tester", "Recorded (UTC)"])
    for t in suite.tests:
        r = results.get(t.id, Result())
        writer.writerow([t.id, t.group, t.title, r.status, r.comment, r.tester, r.recorded_at])
    return buf.getvalue()


_CSS = """
body{font:15px/1.5 system-ui,Segoe UI,Arial,sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem;color:#1b2733}
h1{margin-bottom:.2rem}.muted{color:#5b6b79}table{border-collapse:collapse;width:100%;margin:1rem 0}
th,td{border:1px solid #d5dbe0;padding:.4rem .6rem;text-align:left;vertical-align:top}
th{background:#173447;color:#fff}td.n{text-align:right}
.b{display:inline-block;padding:.05rem .5rem;border-radius:.7rem;font-size:.85em;font-weight:600}
.PASS{background:#c6efce;color:#006100}.FAIL{background:#ffc7ce;color:#9c0006}
.BLOCKED{background:#ffeb9c;color:#9c5700}.SKIP{background:#ededed;color:#595959}
.NOT_RUN{background:#e8eef3;color:#1b2733}
""".strip()


def _badge(status: str) -> str:
    return f'<span class="b {status.replace(" ", "_")}">{escape(status)}</span>'


def render_html(summary: Summary, results: Mapping[str, Result]) -> str:
    s = summary
    rows = "".join(f"<tr><td>{_badge(n)}</td><td class='n'>{s.counts[n]}</td></tr>"
                   for n in STATUS_NAMES)
    groups = "".join(
        f"<tr><td>{escape(g)}</td>" + "".join(f"<td class='n'>{c[n]}</td>" for n in STATUS_NAMES)
        + "</tr>" for g, c in s.by_group)
    detail = "".join(
        f"<tr><td>{escape(t.id)}</td><td>{escape(t.group)}</td><td>{escape(t.title)}</td>"
        f"<td>{_badge(results.get(t.id, Result()).status)}</td>"
        f"<td>{escape(results.get(t.id, Result()).comment)}</td></tr>" for t in s.suite.tests)
    head = "".join(f"<th>{escape(n)}</th>" for n in STATUS_NAMES)
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        f"<title>{escape(s.suite.name)} - report</title><style>{_CSS}</style></head><body>"
        f"<h1>{escape(s.suite.name)}</h1><p class='muted'>Suite {escape(s.suite.id)} "
        f"v{escape(s.suite.version)}</p>"
        f"<p><b>Progress:</b> {_pct(s.progress)} ({s.executed}/{s.total}) &nbsp; "
        f"<b>Pass rate:</b> {_pct(s.pass_rate)}</p>"
        f"<table><tr><th>Status</th><th>Count</th></tr>{rows}</table>"
        f"<h2>By group</h2><table><tr><th>Group</th>{head}</tr>{groups}</table>"
        "<h2>All tests</h2><table><tr><th>ID</th><th>Group</th><th>Test</th><th>Status</th>"
        f"<th>Comment</th></tr>{detail}</table></body></html>\n")

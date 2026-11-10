"""Minimal, dependency-free XLSX writer and reader for the results workbook.

Why hand-written: lab and production PCs often cannot install packages. An
``.xlsx`` file is a ZIP of small XML parts, and this module writes exactly the
parts it needs. The reader is tolerant on purpose - it understands files that
were re-saved by Excel (shared strings, omitted empty cells, other sheet order).
"""
from __future__ import annotations

import os
import posixpath
import re
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional
from xml.sax.saxutils import escape

from .model import DEFAULT_STATUS, STATUSES, Result, normalize_status
from .suite import Suite

RESULTS_SHEET = "Results"
SUMMARY_SHEET = "Summary"
HEADERS = ("ID", "Group", "Test", "Status", "Comment", "Tester", "Recorded (UTC)")
WIDTHS = (14, 20, 60, 14, 55, 18, 22)
EXCEL_CELL_LIMIT = 32767

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
_ILLEGAL_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")
_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)       # reproducible output

# cellXfs indexes (keep in sync with _styles_xml)
S_DEFAULT, S_HEADER, S_WRAP, S_CENTER, S_LABEL, S_PERCENT, S_TITLE = range(7)


# --------------------------------------------------------------------------- #
# Writing
# --------------------------------------------------------------------------- #
def _clean(value: str) -> str:
    return escape(_ILLEGAL_XML.sub("", value)[:EXCEL_CELL_LIMIT])


def _col(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    name = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        name = chr(65 + rem) + name
    return name


def _text(ref: str, value: str, style: int) -> str:
    return (f'<c r="{ref}" s="{style}" t="inlineStr"><is>'
            f'<t xml:space="preserve">{_clean(value)}</t></is></c>')


def _formula(ref: str, formula: str, style: int) -> str:
    return f'<c r="{ref}" s="{style}"><f>{escape(formula)}</f></c>'


def _row(number: int, cells: Iterable[str]) -> str:
    return f'<row r="{number}">{"".join(cells)}</row>'


def _results_sheet(suite: Suite, results: Mapping[str, Result]) -> str:
    last = len(suite.tests) + 1
    rows = [_row(1, (_text(f"{_col(i)}1", h, S_HEADER) for i, h in enumerate(HEADERS)))]
    for n, test in enumerate(suite.tests, 2):
        r = results.get(test.id, Result())
        values = (test.id, test.group, test.title, r.status, r.comment, r.tester, r.recorded_at)
        styles = (S_WRAP, S_WRAP, S_WRAP, S_CENTER, S_WRAP, S_WRAP, S_CENTER)
        rows.append(_row(n, (_text(f"{_col(i)}{n}", v, s)
                             for i, (v, s) in enumerate(zip(values, styles)))))
    cols = "".join(f'<col min="{i}" max="{i}" width="{w}" customWidth="1"/>'
                   for i, w in enumerate(WIDTHS, 1))
    coloured = [s for s in STATUSES if s.fill_color]
    rules = "".join(
        f'<cfRule type="cellIs" dxfId="{i}" priority="{i + 1}" operator="equal">'
        f'<formula>"{s.name}"</formula></cfRule>' for i, s in enumerate(coloured))
    names = ",".join(s.name for s in STATUSES)
    end_col = _col(len(HEADERS) - 1)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<worksheet xmlns="{NS_MAIN}"><sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>'
        f'<dimension ref="A1:{end_col}{last}"/>'
        '<sheetViews><sheetView workbookViewId="0" tabSelected="1">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        '<selection pane="bottomLeft" activeCell="D2" sqref="D2"/></sheetView></sheetViews>'
        '<sheetFormatPr defaultRowHeight="18"/>'
        f'<cols>{cols}</cols><sheetData>{"".join(rows)}</sheetData>'
        f'<autoFilter ref="A1:{end_col}{last}"/>'
        f'<conditionalFormatting sqref="D2:D{last}">{rules}</conditionalFormatting>'
        '<dataValidations count="1"><dataValidation type="list" allowBlank="1" '
        f'showErrorMessage="1" sqref="D2:D{last}"><formula1>"{names}"</formula1>'
        '</dataValidation></dataValidations>'
        '<pageMargins left="0.5" right="0.5" top="0.75" bottom="0.75" header="0.3" footer="0.3"/>'
        '<pageSetup orientation="landscape" fitToWidth="1" fitToHeight="0"/></worksheet>')


def _summary_sheet(suite: Suite, generated_at: str) -> str:
    last = len(suite.tests) + 1
    status_col = f"{RESULTS_SHEET}!$D$2:$D${last}"
    group_col = f"{RESULTS_SHEET}!$B$2:$B${last}"
    rows: List[str] = []
    rows.append(_row(1, [_text("A1", "Test run summary", S_TITLE)]))
    info = (("Suite", suite.name), ("Suite ID", suite.id), ("Version", suite.version),
            ("Last updated (UTC)", generated_at))
    for i, (label, value) in enumerate(info, 3):
        rows.append(_row(i, [_text(f"A{i}", label, S_LABEL), _text(f"B{i}", value, S_DEFAULT)]))

    head = 8
    rows.append(_row(head, [_text(f"A{head}", "Status", S_HEADER),
                            _text(f"B{head}", "Count", S_HEADER),
                            _text(f"C{head}", "Share", S_HEADER)]))
    first = head + 1
    total_row = first + len(STATUSES)
    status_row: Dict[str, int] = {}
    for i, status in enumerate(STATUSES):
        n = first + i
        status_row[status.name] = n
        rows.append(_row(n, [
            _text(f"A{n}", status.name, S_WRAP),
            _formula(f"B{n}", f"COUNTIF({status_col},A{n})", S_CENTER),
            _formula(f"C{n}", f"IFERROR(B{n}/$B${total_row},0)", S_PERCENT)]))
    rows.append(_row(total_row, [
        _text(f"A{total_row}", "Total", S_LABEL),
        _formula(f"B{total_row}", f"SUM(B{first}:B{total_row - 1})", S_CENTER),
        _formula(f"C{total_row}", f"SUM(C{first}:C{total_row - 1})", S_PERCENT)]))

    nr, p, f = status_row[DEFAULT_STATUS], status_row["PASS"], status_row["FAIL"]
    metrics = total_row + 2
    rows.append(_row(metrics, [
        _text(f"A{metrics}", "Executed (everything except NOT RUN)", S_LABEL),
        _formula(f"B{metrics}", f"B{total_row}-B{nr}", S_CENTER)]))
    rows.append(_row(metrics + 1, [
        _text(f"A{metrics + 1}", "Progress (executed / total)", S_LABEL),
        _formula(f"B{metrics + 1}", f"IFERROR(B{metrics}/B{total_row},0)", S_PERCENT)]))
    rows.append(_row(metrics + 2, [
        _text(f"A{metrics + 2}", "Pass rate (PASS / (PASS + FAIL))", S_LABEL),
        _formula(f"B{metrics + 2}", f'IFERROR(B{p}/(B{p}+B{f}),"n/a")', S_PERCENT)]))

    ghead = metrics + 4
    names = [s.name for s in STATUSES]
    rows.append(_row(ghead, [_text(f"{_col(0)}{ghead}", "Group", S_HEADER),
                             _text(f"{_col(1)}{ghead}", "Total", S_HEADER)]
                            + [_text(f"{_col(2 + i)}{ghead}", n, S_HEADER)
                               for i, n in enumerate(names)]))
    for k, group in enumerate(suite.groups(), ghead + 1):
        cells = [_text(f"A{k}", group, S_WRAP),
                 _formula(f"B{k}", f"COUNTIF({group_col},$A{k})", S_CENTER)]
        for i in range(len(names)):
            c = _col(2 + i)
            cells.append(_formula(f"{c}{k}", f"COUNTIFS({group_col},$A{k},{status_col},{c}${ghead})",
                                  S_CENTER))
        rows.append(_row(k, cells))
    end = ghead + len(suite.groups())
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<worksheet xmlns="{NS_MAIN}"><sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>'
        f'<dimension ref="A1:{_col(1 + len(names))}{end}"/>'
        '<sheetViews><sheetView workbookViewId="0"/></sheetViews>'
        '<sheetFormatPr defaultRowHeight="18"/>'
        '<cols><col min="1" max="1" width="40" customWidth="1"/>'
        f'<col min="2" max="{2 + len(names)}" width="14" customWidth="1"/></cols>'
        f'<sheetData>{"".join(rows)}</sheetData>'
        '<pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" header="0.3" footer="0.3"/>'
        '<pageSetup orientation="portrait" fitToWidth="1" fitToHeight="0"/></worksheet>')


def _styles_xml() -> str:
    coloured = [s for s in STATUSES if s.fill_color]
    dxfs = "".join(
        f'<dxf><font><color rgb="{s.font_color}"/></font><fill><patternFill>'
        f'<bgColor rgb="{s.fill_color}"/></patternFill></fill></dxf>' for s in coloured)
    border = ('<border><left style="thin"><color rgb="FFBFBFBF"/></left>'
              '<right style="thin"><color rgb="FFBFBFBF"/></right>'
              '<top style="thin"><color rgb="FFBFBFBF"/></top>'
              '<bottom style="thin"><color rgb="FFBFBFBF"/></bottom></border>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<styleSheet xmlns="{NS_MAIN}">'
        '<numFmts count="1"><numFmt numFmtId="164" formatCode="0.0%"/></numFmts>'
        '<fonts count="4"><font><sz val="11"/><name val="Calibri"/></font>'
        '<font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font>'
        '<font><b/><sz val="11"/><name val="Calibri"/></font>'
        '<font><b/><color rgb="FF173447"/><sz val="14"/><name val="Calibri"/></font></fonts>'
        '<fills count="3"><fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FF173447"/>'
        '<bgColor indexed="64"/></patternFill></fill></fills>'
        f'<borders count="2"><border/>{border}</borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="7">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" '
        'applyBorder="1" applyAlignment="1"><alignment vertical="center"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" '
        'applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" '
        'applyAlignment="1"><alignment horizontal="center" vertical="top"/></xf>'
        '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
        '<xf numFmtId="164" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" '
        'applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="top"/></xf>'
        '<xf numFmtId="0" fontId="3" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
        '</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        f'<dxfs count="{len(coloured)}">{dxfs}</dxfs></styleSheet>')


def _workbook_xml(last_row: int) -> str:
    end_col = _col(len(HEADERS) - 1)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<workbook xmlns="{NS_MAIN}" xmlns:r="{NS_REL}"><sheets>'
        f'<sheet name="{RESULTS_SHEET}" sheetId="1" r:id="rId1"/>'
        f'<sheet name="{SUMMARY_SHEET}" sheetId="2" r:id="rId2"/></sheets>'
        '<definedNames>'
        f'<definedName name="_xlnm._FilterDatabase" localSheetId="0" hidden="1">'
        f'{RESULTS_SHEET}!$A$1:${end_col}${last_row}</definedName>'
        f'<definedName name="_xlnm.Print_Titles" localSheetId="0">{RESULTS_SHEET}!$1:$1</definedName>'
        '</definedNames><calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>')


_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    '<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
    '</Types>')
_ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<Relationships xmlns="{NS_PKG}"><Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="xl/workbook.xml"/></Relationships>')
_WORKBOOK_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<Relationships xmlns="{NS_PKG}">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>'
    '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    '</Relationships>')


def write_workbook(path: "str | Path", suite: Suite, results: Mapping[str, Result],
                   generated_at: str) -> None:
    """Write the workbook atomically (temp file + ``os.replace``).

    Raises ``PermissionError`` on Windows if Excel has the target open; the
    existing file is never left half-written.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    parts = {
        "[Content_Types].xml": _CONTENT_TYPES,
        "_rels/.rels": _ROOT_RELS,
        "xl/workbook.xml": _workbook_xml(len(suite.tests) + 1),
        "xl/_rels/workbook.xml.rels": _WORKBOOK_RELS,
        "xl/styles.xml": _styles_xml(),
        "xl/worksheets/sheet1.xml": _results_sheet(suite, results),
        "xl/worksheets/sheet2.xml": _summary_sheet(suite, generated_at),
    }
    fd, tmp = tempfile.mkstemp(suffix=".tmp", dir=path.parent)
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for name, data in parts.items():
                info = zipfile.ZipInfo(name, date_time=_FIXED_ZIP_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o600 << 16
                info.create_system = 3          # same value on every OS
                z.writestr(info, data)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #
_COL_RE = re.compile(r"^([A-Z]+)(\d+)$")


def _q(tag: str) -> str:
    return f"{{{NS_MAIN}}}{tag}"


def _all_text(element: ET.Element) -> str:
    return "".join(t.text or "" for t in element.iter(_q("t")))


def _locate_sheet(z: zipfile.ZipFile, sheet_name: str) -> str:
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rid: Optional[str] = None
    for sheet in wb.iter(_q("sheet")):
        if sheet.get("name") == sheet_name:
            rid = sheet.get(f"{{{NS_REL}}}id")
    if rid is None:
        raise ValueError(f"workbook has no sheet named '{sheet_name}'")
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    for rel in rels:
        if rel.get("Id") == rid:
            target = rel.get("Target", "")
            return target.lstrip("/") if target.startswith("/") else posixpath.join("xl", target)
    raise ValueError(f"broken relationship {rid} in workbook")


def _shared_strings(z: zipfile.ZipFile) -> List[str]:
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    return [_all_text(si) for si in root.iter(_q("si"))]


def _col_index(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_results(path: "str | Path") -> Dict[str, Result]:
    """Return ``{test_id: Result}`` from a results workbook ({} if it does not exist)."""
    path = Path(path)
    if not path.exists():
        return {}
    with zipfile.ZipFile(path) as z:
        sheet = ET.fromstring(z.read(_locate_sheet(z, RESULTS_SHEET)))
        shared = _shared_strings(z)
    out: Dict[str, Result] = {}
    for row in sheet.iter(_q("row")):
        if row.get("r") == "1":
            continue
        values: Dict[int, str] = {}
        for c in row.findall(_q("c")):
            m = _COL_RE.match(c.get("r", ""))
            if not m:
                continue
            kind = c.get("t")
            if kind == "inlineStr":
                text = _all_text(c)
            else:
                v = c.find(_q("v"))
                text = "" if v is None or v.text is None else v.text
                if kind == "s" and text:
                    text = shared[int(text)]
            values[_col_index(m.group(1))] = text
        test_id = values.get(0, "").strip()
        if not test_id:
            continue
        out[test_id] = Result(
            status=normalize_status(values.get(3, "")) or DEFAULT_STATUS,
            comment=values.get(4, ""), tester=values.get(5, ""), recorded_at=values.get(6, ""))
    return out

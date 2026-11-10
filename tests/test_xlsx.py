import importlib.util
import tempfile
import unittest
import zipfile
from pathlib import Path

import helpers
from qa_runner.model import Result
from qa_runner.suite import load_suite, parse_suite
from qa_runner.xlsx import read_results, write_workbook


class WorkbookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.book = Path(self.tmp.name) / "book.xlsx"
        self.suite = load_suite(helpers.DEMO_SUITE)

    def test_roundtrip_preserves_results(self):
        results = {"BOOT-001": Result("PASS", "fine", "Ann", "2026-01-01T10:00:00Z"),
                   "NET-002": Result("FAIL", "no link\nsecond line", "Bo", "2026-01-01T11:00:00Z")}
        write_workbook(self.book, self.suite, results, "2026-01-01T11:00:00Z")
        back = read_results(self.book)
        self.assertEqual(back["BOOT-001"], results["BOOT-001"])
        self.assertEqual(back["NET-002"], results["NET-002"])
        self.assertEqual(back["STO-003"], Result())          # untouched test = NOT RUN
        self.assertEqual(len(back), 12)

    def test_missing_file_reads_as_empty(self):
        self.assertEqual(read_results(self.book), {})

    def test_special_and_illegal_characters(self):
        nasty = 'a & b < c > d "q" \x07 end \u00e9 \u00b0C'
        write_workbook(self.book, self.suite, {"BOOT-001": Result("FAIL", nasty)}, "t")
        self.assertEqual(read_results(self.book)["BOOT-001"].comment, nasty.replace("\x07", ""))

    def test_huge_comment_is_truncated_to_excel_limit(self):
        write_workbook(self.book, self.suite, {"BOOT-001": Result("FAIL", "x" * 40000)}, "t")
        self.assertEqual(len(read_results(self.book)["BOOT-001"].comment), 32767)

    def test_output_is_reproducible(self):
        a, b = Path(self.tmp.name) / "a.xlsx", Path(self.tmp.name) / "b.xlsx"
        for p in (a, b):
            write_workbook(p, self.suite, {"BOOT-001": Result("PASS")}, "2026-01-01T00:00:00Z")
        self.assertEqual(a.read_bytes(), b.read_bytes())

    def test_no_temp_files_left_behind(self):
        write_workbook(self.book, self.suite, {}, "t")
        self.assertEqual([p.name for p in Path(self.tmp.name).iterdir()], ["book.xlsx"])

    def test_package_structure(self):
        write_workbook(self.book, self.suite, {}, "t")
        with zipfile.ZipFile(self.book) as z:
            self.assertIsNone(z.testzip())
            names = set(z.namelist())
            sheet = z.read("xl/worksheets/sheet1.xml").decode()
            summary = z.read("xl/worksheets/sheet2.xml").decode()
        self.assertTrue({"[Content_Types].xml", "xl/workbook.xml", "xl/styles.xml",
                         "xl/worksheets/sheet1.xml", "xl/worksheets/sheet2.xml"} <= names)
        self.assertIn('ref="A1:G13"', sheet)                 # 12 tests + header
        self.assertIn("<dataValidation", sheet)
        self.assertEqual(sheet.count("<cfRule"), 4)           # 4 coloured statuses
        self.assertIn("COUNTIFS(Results!$B$2:$B$13", summary)
        self.assertIn("IFERROR", summary)

    def test_group_names_with_quotes_do_not_break_formulas(self):
        raw = helpers.minimal_suite_dict()
        raw["tests"][0]["group"] = 'Q"uote & <co>'
        suite = parse_suite(raw)
        write_workbook(self.book, suite, {}, "t")
        self.assertEqual(read_results(self.book)["T-1"], Result())

    def test_reads_files_saved_by_excel(self):
        """Excel rewrites text as shared strings, drops empty cells and may reorder sheets."""
        wb = ('<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
              'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
              '<sheet name="Summary" sheetId="2" r:id="rId2"/><sheet name="Results" sheetId="1" r:id="rId1"/>'
              '</sheets></workbook>')
        rels = ('<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="x" Target="/xl/worksheets/sheet9.xml"/>'
                '<Relationship Id="rId2" Type="x" Target="worksheets/sheet2.xml"/></Relationships>')
        sst = ('<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
               '<si><t>ID</t></si><si><t>T-1</t></si><si><t>Pass</t></si>'
               '<si><r><t>rich </t></r><r><t>comment</t></r></si><si><t>Ann</t></si></sst>')
        sheet = ('<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                 '<row r="1"><c r="A1" t="s"><v>0</v></c></row>'
                 # B,C and G omitted (empty); status typed in lower case by a human
                 '<row r="2"><c r="A2" t="s"><v>1</v></c><c r="D2" t="s"><v>2</v></c>'
                 '<c r="E2" t="s"><v>3</v></c><c r="F2" t="s"><v>4</v></c></row>'
                 '</sheetData></worksheet>')
        with zipfile.ZipFile(self.book, "w") as z:
            z.writestr("xl/workbook.xml", wb)
            z.writestr("xl/_rels/workbook.xml.rels", rels)
            z.writestr("xl/sharedStrings.xml", sst)
            z.writestr("xl/worksheets/sheet9.xml", sheet)
        self.assertEqual(read_results(self.book),
                         {"T-1": Result("PASS", "rich comment", "Ann", "")})

    def test_missing_results_sheet_is_a_clear_error(self):
        with zipfile.ZipFile(self.book, "w") as z:
            z.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                                           '<sheets/></workbook>')
        with self.assertRaises(ValueError) as ctx:
            read_results(self.book)
        self.assertIn("Results", str(ctx.exception))

    @unittest.skipUnless(importlib.util.find_spec("openpyxl"), "openpyxl not installed")
    def test_opens_in_openpyxl(self):
        import openpyxl
        write_workbook(self.book, self.suite, {"BOOT-001": Result("PASS")}, "t")
        wb = openpyxl.load_workbook(self.book)
        self.assertEqual(wb.sheetnames, ["Results", "Summary"])
        self.assertEqual(wb["Results"].freeze_panes, "A2")
        self.assertEqual(wb["Results"]["D2"].value, "PASS")


if __name__ == "__main__":
    unittest.main()

"""The dashboard's Excel export lets the user choose commodities and lays the
workbook out for reading in Excel (commodity sheets, filters, frozen headers)."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from prometheus_core import exec_report_html as h  # noqa: E402

T = h._TEMPLATE


class ExportPickerTests(unittest.TestCase):
    def test_picker_markup_comes_before_the_script(self):
        self.assertIn('id="xDlg"', T)
        self.assertLess(T.index('id="xDlg"'), T.index("<script>"))
        for hook in ('id="xList"', 'id="xAll"', 'id="xNone"', 'id="xPer"', 'id="xGo"', 'id="xCancel"', 'aria-modal="true"'):
            self.assertIn(hook, T)
        self.assertIn('$("bXlsx").addEventListener("click", openXlsxDlg)', T)

    def test_workbook_layout(self):
        for part in ("function viewFor(bases)", "function commoditySheet(b, vb)", "<autoFilter ref=",
                     'state="frozen"', "<hyperlinks>", "_xlnm._FilterDatabase", "← Back to Summary",
                     "By commodity", 'numFmtId="4"'):
            self.assertIn(part, T)

    def test_sheet_names_are_excel_safe(self):
        self.assertIn("const sheetName = n => String(n).replace(", T)
        self.assertIn(".slice(0, 31)", T)


if __name__ == "__main__":
    unittest.main()

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


class SavingsDayTableTests(unittest.TestCase):
    """Savings vs local daily rows: excl. block, then freight + local transport, then incl. block."""

    def test_column_order(self):
        i = T.index("const SV_DAY_TH")
        th = T[i:T.index(";", T.index("Savings incl. EGP</th>", i))]
        order = ["= Landed excl. transport", "Local excl. (that day)", "Savings excl. EGP/MT", "Savings excl. EGP",
                 "+ Inland freight", "= Landed incl. transport", "+ Local transport", "Local incl. (that day)",
                 "Savings incl. EGP/MT", "Savings incl. EGP"]
        pos = [th.index(x) for x in order]
        self.assertEqual(pos, sorted(pos))
        self.assertIn("${SV_DAY_TH}", T)
        self.assertIn("svDayTot(c)", T)

    def test_export_sheet_follows_the_same_order(self):
        self.assertIn("[...grp(SCN.excl), ...tr, ...grp(SCN.incl)]", T)


if __name__ == "__main__":
    unittest.main()

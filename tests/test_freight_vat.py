"""App-level tests for the freight VAT entry modes (Detailed vs All-In) in
the Contract editor. Run via: python -m unittest discover -s tests

These exercise the real Tkinter App so they cover the full save/load path,
not just the pure freight_incl_vat() formula (already covered in
test_fifo_inventory.py). Needs a display; on Windows (where this app runs)
that's always available. In this repo's Linux CI/dev sandbox it's run
under Xvfb.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    import tkinter  # noqa: F401
    _HAS_TK = True
except Exception:
    _HAS_TK = False


@unittest.skipUnless(_HAS_TK, "tkinter not available in this environment")
class TestFreightVatModes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import Prometheus_V10_8_15 as P
        cls.P = P
        cls.app = P.App()
        cls.app.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.app.destroy()

    def _new_contract_form(self, name):
        app = self.app
        app._contracts_prepare_new()
        app.c_name_var.set(name)
        app.c_supplier_var.set("TESTSUP")
        app.c_commodity_var.set("CORN")
        app.c_origin_var.set("ARGENTINA")
        app.c_status_var.set("Open")
        app.c_qty_var.set("1000")

    def test_detailed_mode_adds_14_percent_vat_on_save(self):
        self._new_contract_form("VAT-DETAILED")
        self.app.c_freight_mode_var.set("detailed")
        self.app.c_freight_vat_pct_var.set("14")
        self.app.c_freight_var.set("400")
        self.app.add_contract()
        cid = next(cid for cid, c in self.app.state_obj["contracts"].items()
                   if c.get("name") == "VAT-DETAILED")
        c = self.app.state_obj["contracts"][cid]
        self.assertAlmostEqual(c["freight_egp_mt"], 456.0)
        self.assertEqual(c["freight_mode"], "detailed")
        self.assertAlmostEqual(c["freight_base_egp_mt"], 400.0)

    def test_all_in_mode_does_not_double_count_vat(self):
        self._new_contract_form("VAT-ALLIN")
        self.app.c_freight_mode_var.set("all_in")
        self.app.c_freight_var.set("456")
        self.app.add_contract()
        cid = next(cid for cid, c in self.app.state_obj["contracts"].items()
                   if c.get("name") == "VAT-ALLIN")
        c = self.app.state_obj["contracts"][cid]
        self.assertAlmostEqual(c["freight_egp_mt"], 456.0)
        self.assertNotAlmostEqual(c["freight_egp_mt"], 456.0 * 1.14)

    def _load_via_tree(self, cid):
        """Refresh the contracts tree, select `cid`, and load it into the
        editor -- the same path a real click on a Contracts row takes."""
        self.app.refresh_contracts_tree()
        self.app.contract_tree.selection_set(cid)
        self.app.load_contract_from_tree()

    def test_loading_pre_existing_contract_defaults_to_all_in(self):
        # Simulate a contract saved before this feature existed: it has a
        # freight_egp_mt but no freight_mode at all.
        cid = "LEGACY-1"
        self.app.state_obj["contracts"][cid] = {
            "name": "Legacy contract", "supplier": "SUP", "commodity": "CORN",
            "origin": "ARGENTINA", "status": "Open", "qty_mt": 500,
            "freight_egp_mt": 400.0,  # a historical, already-final number
        }
        self._load_via_tree(cid)
        self.assertEqual(self.app.c_freight_mode_var.get(), "all_in")
        self.assertEqual(self.app.c_freight_var.get(), "400.0")

    def test_resaving_legacy_contract_without_touching_freight_preserves_value(self):
        cid = "LEGACY-2"
        self.app.state_obj["contracts"][cid] = {
            "name": "Legacy contract 2", "supplier": "SUP", "commodity": "CORN",
            "origin": "ARGENTINA", "status": "Open", "qty_mt": 500,
            "freight_egp_mt": 400.0,
        }
        self._load_via_tree(cid)
        # User edits an unrelated field and saves -- freight box untouched.
        self.app.c_note_var.set("touched only the note")
        self.app.update_contract()
        c = self.app.state_obj["contracts"][cid]
        self.assertAlmostEqual(c["freight_egp_mt"], 400.0)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib.util
import pathlib
import unittest


class DesktopSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project = pathlib.Path(__file__).resolve().parents[1]
        cls.path = cls.project / "Prometheus_V10_9_2.py"
        spec = importlib.util.spec_from_file_location("prometheus_desktop_modern_contracts_workspace", cls.path)
        cls.module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(cls.module)

    def test_organized_desktop_file_compiles(self):
        source = self.path.read_text(encoding="utf-8")
        compile(source, str(self.path), "exec")

    def test_desktop_imports_and_delegates_to_core(self):
        self.assertEqual(self.module.APP_BUILD, "V10.9.2-inventory-vs-market")
        result = self.module.run_decision_engine({"commodity": "CORN"})
        self.assertEqual(result["action"], "INSUFFICIENT_DATA")

    def test_legacy_copies_are_preserved(self):
        self.assertTrue((self.project / "legacy" / "V10_4_Frozen.py").exists())
        self.assertTrue((self.project / "legacy" / "V10_5_Frozen.py").exists())
        self.assertTrue((self.project / "legacy" / "V10_7_Frozen.py").exists())
        self.assertTrue((self.project / "legacy" / "V10_8_1_Frozen.py").exists())
        self.assertTrue((self.project / "legacy" / "V10_8_2_Frozen.py").exists())
        self.assertTrue((self.project / "legacy" / "V10_8_4_Frozen.py").exists())
        self.assertTrue((self.project / "legacy" / "V10_8_5_Frozen.py").exists())
        self.assertTrue((self.project / "legacy" / "V10_8_7_Frozen.py").exists())
        self.assertTrue((self.project / "legacy" / "V10_8_8_Frozen.py").exists())
        self.assertTrue((self.project / "legacy" / "V10_8_9_Frozen.py").exists())
        self.assertTrue((self.project / "legacy" / "V10_8_10_Frozen.py").exists())
        self.assertTrue((self.project / "legacy" / "V10_8_11_Frozen.py").exists())
        self.assertTrue((self.project / "legacy" / "V10_8_12_Frozen.py").exists())
        self.assertTrue((self.project / "legacy" / "V10_9_1_Frozen.py").exists())


    def test_inventory_vs_market_view_is_present_and_fifo_based(self):
        source = self.path.read_text(encoding="utf-8")
        self.assertIn('text="Inventory vs Market"', source)
        self.assertIn('def _inventory_market_rows', source)
        self.assertIn('remaining_mt', source)
        self.assertIn('FIFO Cost', source)
        self.assertIn('CBOT Replacement', source)
        self.assertIn('Edge vs Local/MT', source)
        self.assertIn('Edge vs CBOT/MT', source)
        self.assertIn('Premium missing — replacement incomplete', source)



    def test_quick_snapshot_excel_uses_effective_corn_factor(self):
        import tempfile

        snap = {
            "snapshot_id": "S-FACTOR",
            "commodity": "CORN",
            "origin": "USA",
            "qty_mt": 1000,
            "fx": 50,
            "local_egp_mt": 12000,
            "cbot": 450,
            "premium_usd_mt": 25,
            "import_usd_mt": (450 + 25) * self.module.CORN_FACTOR,
            "finance_days": 0,
            "interest_rate": 0,
            "supplier_direct_egp_mt": 0,
            "supplier_indirect_egp_mt": 0,
            # Legacy snapshots stored bushels/MT here.  The export must not
            # present 39.37 as the financial conversion factor.
            "conversion_type": "bu_per_mt",
            "conversion_value": 39.37,
        }
        with tempfile.TemporaryDirectory() as td:
            fp = pathlib.Path(td) / "quick_snapshot.xlsx"
            self.assertTrue(self.module.export_snapshot_excel(str(fp), snap))
            wb = self.module.openpyxl.load_workbook(fp, data_only=False)
            ws = wb["Snapshot"]
            labels = {ws.cell(r, 1).value: r for r in range(1, ws.max_row + 1)}
            factor_row = labels["Conversion Factor Used"]
            premium_mode_row = labels["Premium Mode"]
            import_row = labels["Import USD/MT"]
            self.assertAlmostEqual(ws.cell(factor_row, 2).value, 0.3937, places=8)
            self.assertEqual(ws.cell(premium_mode_row, 2).value, "CBOT_UNIT")
            formula = ws.cell(import_row, 2).value
            self.assertIn(f"B{factor_row}", formula)
            self.assertNotIn("39.37", formula)
            self.assertNotIn("CORN Locked Factor", labels)


    def test_home_commodity_cards_are_visible_and_not_overlapped(self):
        source = self.path.read_text(encoding="utf-8")
        self.assertIn("Commodity Performance", source)
        self.assertIn("Open Exposure by Commodity", source)
        self.assertIn("Data Quality & Quick Links", source)
        self.assertIn("comm_portfolio.grid(row=2", source)
        # Section order is the invariant; the sections themselves are now
        # built by `_hd_section` rather than as raw LabelFrames.
        self.assertIn("row=7, sticky=\"nsew\")", source)         # open MTM
        self.assertIn("\"Closed contracts only\", row=8", source)  # scorecard
        self.assertIn("row=9, sticky=\"nsew\")", source)         # scenarios

    def test_home_is_themed_through_the_shared_palette(self):
        """Home used to be a hand-painted dark cockpit sitting above light
        ttk frames, which is why it matched neither the rest of the app nor
        itself. It now resolves every colour through `_hd_theme()`."""
        source = self.path.read_text(encoding="utf-8")
        self.assertIn("CEO Dashboard", source)
        self.assertIn("Open Exposure by Commodity", source)
        self.assertIn("Top Contracts / Recent Decisions", source)
        self.assertIn("Data Quality & Quick Links", source)
        self.assertIn("def _hd_theme", source)
        self.assertIn("_HOME_LEGACY_COLOURS", source)
        builder = source[source.index("def _build_home_dashboard"):
                         source.index("def _hd_make_tree")]
        # The legacy navy may only survive inside the classic fallback map.
        for legacy in ("#07111f", "#0b1728", "#06101d", "#0f172a"):
            self.assertNotIn(legacy, builder,
                             f"{legacy} is hardcoded in the Home builder")

    # ── FIFO cost resolution ──────────────────────────────────────────
    def _cost_app(self, contract):
        """An App with just enough state to price one contract."""
        app = self.module.App.__new__(self.module.App)
        app.state_obj = {
            "contracts": {"C1": contract},
            "commodities": {},
            "local_prices": [],
            "market_data": {"cbot_quotes": {"CORN": 532.75, "SBM": 305.0},
                            "fx": {"price": 50.9620}},
        }
        return app

    @staticmethod
    def _corn_contract(**over):
        base = {
            "name": "460/20048300", "commodity": "CORN-BRZ", "origin": "BRAZIL",
            "qty_mt": 2000, "status": "Open", "premium_cents": 194.25,
            "delivery_date": "2026-08-20", "discharge_egp_mt": 120,
            "clearance_egp_mt": 60, "freight_egp_mt": 485,
        }
        base.update(over)
        return base

    def test_unpriced_contract_without_a_saved_cif_still_gets_a_cost(self):
        """`priced` defaults to True and is usually absent, so a contract with
        no saved CIF used to produce no cost at all — the table showed
        UNPRICED in one column and an empty FIFO Cost in the next."""
        for label, contract in (
            ("priced absent", self._corn_contract()),
            ("priced=True", self._corn_contract(priced=True)),
            ("priced=False", self._corn_contract(priced=False)),
        ):
            app = self._cost_app(contract)
            economics = app._hd_cost_for_contract(
                "C1", contract, use_latest_fx=False, fx_mode="locked")
            self.assertIsNotNone(economics["own_after"], label)
            self.assertEqual(economics["cif_basis"], "live", label)
            # (532.75 + 194.25) x 0.3937 x 50.9620 + 120 + 60 + 485
            self.assertAlmostEqual(economics["own_after"], 15251, delta=5)

    def test_a_real_saved_cif_is_never_replaced_by_a_live_derivation(self):
        contract = self._corn_contract(priced=True, cif_usd_mt=286.12)
        app = self._cost_app(contract)
        economics = app._hd_cost_for_contract(
            "C1", contract, use_latest_fx=False, fx_mode="locked")
        self.assertEqual(economics["cif_basis"], "saved")
        self.assertAlmostEqual(economics["cif"], 286.12, places=4)

    def test_unpriced_cost_uses_the_commoditys_own_conversion_factor(self):
        """0.3937 is corn's factor; SBM converts at 1.1023 short tons/MT."""
        contract = self._corn_contract(commodity="SBM", premium_cents=20.0,
                                       priced=False)
        app = self._cost_app(contract)
        economics = app._hd_cost_for_contract(
            "C1", contract, use_latest_fx=False, fx_mode="locked")
        self.assertAlmostEqual(economics["cif"],
                               (305.0 + 20.0) * self.module.SBM_ST_PER_MT,
                               places=4)
        self.assertNotIn("0.3937", economics["cif_formula"])

    def test_a_derived_fifo_cost_is_labelled_indicative(self):
        source = self.path.read_text(encoding="utf-8")
        self.assertIn("FIFO cost is indicative", source)
        self.assertIn('r.get("fifo_cost_basis") == "live"', source)

    def test_fifo_cost_derivation_is_spelled_out(self):
        """Every cost on the table must be auditable from the row itself."""
        contract = self._corn_contract()
        app = self._cost_app(contract)
        derived = app._fifo_cost_formula(app._hd_cost_for_contract(
            "C1", contract, use_latest_fx=False, fx_mode="locked"))
        self.assertIn("532.75", derived)          # the board it came from
        self.assertIn("194.25", derived)          # the premium
        self.assertIn("0.3937", derived)          # the conversion factor
        self.assertIn("50.9620", derived)         # the FX actually used
        self.assertIn("665", derived)             # freight + discharge + clearance
        self.assertIn("indicative", derived)
        # The grid form spells the fees out as addends — a lump total only
        # raises the question of what is in it — and leaves the indicative
        # wording to the value's "~" and the row warning.
        short = app._fifo_cost_formula(app._hd_cost_for_contract(
            "C1", contract, use_latest_fx=False, fx_mode="locked"), compact=True)
        self.assertIn("FX 50.9620", short)
        self.assertIn("frt 485", short)
        self.assertIn("dis 120", short)
        self.assertIn("clr 60", short)
        self.assertNotIn("indicative", short)

        fixed = self._corn_contract(priced=True, cif_usd_mt=286.12)
        app = self._cost_app(fixed)
        text = app._fifo_cost_formula(app._hd_cost_for_contract(
            "C1", fixed, use_latest_fx=False, fx_mode="locked"))
        self.assertIn("Fixed CIF 286.12", text)
        self.assertNotIn("indicative", text)

    def test_derivation_shows_the_contracts_own_fx_not_todays(self):
        """The cost uses locked FX while the table's FX column shows today's;
        the derivation is where that difference becomes visible."""
        contract = self._corn_contract(priced=True, cif_usd_mt=286.12,
                                       delivery_fx=48.5)
        app = self._cost_app(contract)
        text = app._fifo_cost_formula(app._hd_cost_for_contract(
            "C1", contract, use_latest_fx=False, fx_mode="locked"))
        self.assertIn("FX 48.5000", text)
        self.assertNotIn("50.9620", text)

    def test_derivation_explains_a_missing_cost_instead_of_going_blank(self):
        contract = self._corn_contract(premium_cents=None)
        app = self._cost_app(contract)
        economics = app._hd_cost_for_contract(
            "C1", contract, use_latest_fx=False, fx_mode="locked")
        self.assertIsNone(economics["own_after"])
        self.assertIn("No fixed CIF", app._fifo_cost_formula(economics))

    def test_inventory_table_and_export_carry_the_derivation_column(self):
        source = self.path.read_text(encoding="utf-8")
        self.assertIn('("FIFO_Cost_Basis",620,"w")', source)
        self.assertIn('"How the FIFO Cost is built"', source)
        self.assertIn('r.get("fifo_cost_formula")', source)
        self.assertIn('r.get("fifo_cost_formula_short")', source)
        # Every row kind carries it: contract lots, subtotals, physical lots.
        self.assertIn("quantity-weighted across the lots below", source)
        self.assertIn("Physical adjustment — no contract economics", source)
        # The Excel filter range must follow the header, not a fixed letter.
        self.assertIn("get_column_letter(len(hdr))", source)
        self.assertNotIn('auto_filter.ref=f"A4:V', source)

    # ── Sideways scrolling ────────────────────────────────────────────
    def test_shift_wheel_scrolls_the_table_not_the_width_locked_page(self):
        source = self.path.read_text(encoding="utf-8")
        handler = source[source.index("def _page_scroll_shift_mousewheel"):]
        handler = handler[:handler.index("def _build_tabs")]
        # The table must be consulted before the page canvas.
        self.assertLess(handler.index("Treeview"), handler.index("_page_scroll_canvas_for_widget"))
        self.assertIn("TREE_HSCROLL_PIXELS", handler)
        self.assertIn("<Shift-Button-4>", source)
        self.assertIn("<Shift-Button-5>", source)

    def test_calculate_pages_are_scrollable(self):
        source = self.path.read_text(encoding="utf-8")
        self.assertIn("self.tab_single = self._make_scrollable_tab(self.tab_single_page", source)
        self.assertIn("self.tab_future = self._make_scrollable_tab(self.tab_future_page", source)

    def test_wheel_units_cover_windows_and_x11(self):
        app = self.module.App.__new__(self.module.App)

        class _E:
            def __init__(self, delta=0, num=None):
                self.delta, self.num = delta, num

        self.assertEqual(app._wheel_units(_E(num=4)), -1)
        self.assertEqual(app._wheel_units(_E(num=5)), 1)
        self.assertEqual(app._wheel_units(_E(delta=-120)), 1)
        self.assertEqual(app._wheel_units(_E(delta=120)), -1)
        self.assertEqual(app._wheel_units(_E(delta=-40)), 1)

    def test_previous_ceo_dashboard_is_preserved(self):
        self.assertTrue((self.project / "legacy" / "V10_8_13_Frozen.py").exists())

    def test_basis_tracker_has_modern_workspace(self):
        source = self.path.read_text(encoding="utf-8")
        self.assertIn("Basis Intelligence", source)
        self.assertIn("Basis.TNotebook", source)
        self.assertIn("top_workspace = tk.Frame(body", source)
        self.assertIn("Double-click or press Enter", source)
        self.assertIn("contract_xsb", source)
        self.assertIn("local_xsb", source)
        self.assertIn("_force_viewport_width", source)

    def test_basis_tracker_has_separate_contract_and_local_views(self):
        source = self.path.read_text(encoding="utf-8")
        self.assertIn("self.basis_contract_tree = ttk.Treeview", source)
        self.assertIn("self.basis_local_tree = ttk.Treeview", source)
        self.assertIn("self.basis_purchase_tree = ttk.Treeview", source)
        self.assertIn("def _basis_open_local_record", source)
        self.assertIn("def _basis_open_local_purchase_record", source)
        self.assertIn("Contracts · agreed basis", source)
        self.assertIn("Local market · implied basis", source)
        self.assertIn("Local purchases · actual basis", source)

    def test_basis_row_formatters_keep_contract_and_local_fields_distinct(self):
        app = self.module.App.__new__(self.module.App)
        contract = app._basis_contract_row_values({
            "kind": "CONTRACT",
            "date": "2026-07-01",
            "contract": "C0042 Lot 1",
            "origin": "BRAZIL",
            "contract_status": "Open",
            "qty_mt": 10_000,
            "contract_price_egp_mt": 20_469.50,
            "contract_basis": 25,
            "implied_basis": 30,
            "spread": -5,
            "data_status": "Complete",
        })
        local = app._basis_local_row_values({
            "kind": "market",
            "date": "2026-07-01",
            "commodity": "CORN",
            "local_egp_mt": 12_000,
            "expenses_egp_mt": 850,
            "fx": 50.25,
            "cbot": 440,
            "implied_basis": 30,
            "data_status": "Complete",
        })
        self.assertEqual(contract[1], "C0042 Lot 1")
        self.assertEqual(contract[6], "20,469.50")
        self.assertEqual(contract[13], "At/below market")
        self.assertEqual(local[1], "CORN")
        self.assertEqual(local[2], "12,000")
        self.assertEqual(local[6], "30.00")

    def test_argentina_and_brazil_share_the_same_basis_color(self):
        app = self.module.App.__new__(self.module.App)
        self.assertEqual(app._basis_origin_color("ARGENTINA"),
                         app._basis_origin_color("BRAZIL"))
        self.assertEqual(app._basis_origin_legend_label("ARGENTINA"),
                         "ARGENTINA / BRAZIL")
        self.assertEqual(app._basis_origin_legend_label("BRAZIL"),
                         "ARGENTINA / BRAZIL")

    def test_local_purchase_is_added_as_a_separate_basis_point(self):
        app = self.module.App.__new__(self.module.App)
        app.state_obj = {
            "ui": {"basis_expenses_egp_mt": 850},
            "local_prices": [],
            "local_purchases": [{
                "id": 7, "date": "2026-07-01", "supplier": "Local Supplier",
                "commodity": "CORN", "qty_mt": 500, "price_egp_mt": 12000,
                "transport_egp_mt": 300, "cbot_ref": 440, "fx_ref": 50,
            }],
            "contracts": {}, "cbot_history": [], "fx_history": [], "snapshots": [],
        }
        rows = app._basis_enriched_rows("CORN", "ALL")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["kind"], "LOCAL_PURCHASE")
        self.assertEqual(row["purchase_id"], 7)
        self.assertEqual(row["local_egp_mt"], 12300)
        expected = ((12300 - 850) / 50) / self.module.CORN_FACTOR - 440
        self.assertAlmostEqual(row["implied_basis"], expected, places=8)
        values = app._basis_purchase_row_values(row)
        self.assertEqual(values[1], 7)
        self.assertEqual(values[2], "Local Supplier")
        self.assertEqual(values[8], f"{expected:,.2f}")

    def test_savings_tracker_has_filtered_basis_excel_export(self):
        source = self.path.read_text(encoding="utf-8")
        self.assertIn("Export Basis Excel", source)
        self.assertIn("def export_savings_basis_excel", source)
        self.assertIn("Savings filters:", source)
        self.assertIn("local market and actual-purchase context", source)

    def test_contracts_tab_has_modern_command_center(self):
        source = self.path.read_text(encoding="utf-8")
        self.assertIn("Contract Portfolio", source)
        self.assertIn("Contracts.Treeview", source)
        self.assertIn("def _toggle_contract_editor", source)
        self.assertIn("def _toggle_contract_history", source)
        self.assertIn("Selected Contract Workspace", source)

    def test_home_commodity_options_are_dynamic_and_deduplicated(self):
        app = self.module.App.__new__(self.module.App)
        app.state_obj = {
            "commodities": {"CORN": {}, "CORN-BRZ": {}, "WHEAT": {}, "SFM": {}},
            "contracts": {"C1": {"commodity": "SOYBEAN"}},
            "local_prices": [{"commodity": "DDGS"}],
        }
        options = app._home_commodity_options()
        self.assertEqual(options.count("CORN"), 1)
        self.assertIn("WHEAT", options)
        self.assertIn("SOYBEAN", options)
        self.assertIn("DDGS", options)
        self.assertNotIn("CORN-BRZ", options)


    def test_ceo_home_metrics_keep_realized_and_open_separate(self):
        app = self.module.App.__new__(self.module.App)
        app.state_obj = {
            "commodities": {"CORN": {}},
            "contracts": {
                "CLOSED": {"commodity": "CORN", "status": "Closed",
                           "qty_mt": 200, "priced": True, "cif_usd_mt": 180},
                "OPEN": {"commodity": "CORN", "status": "Open",
                         "qty_mt": 100, "remaining_mt": 100, "priced": False,
                         "freight_egp_mt": 100,
                         "pricing_lots": [{"date": "2026-07-01", "qty_mt": 40}]},
            },
            "consumption_log": [],
        }
        app._sv_collect_savings_rows = lambda *args: ([{
            "qty": 200, "own_after": 9000, "local": 10000,
            "realized_date": "2026-07-01",
        }], {"grand_sav": 200000, "grand_qty": 200,
              "counted": 1, "warnings": 0})
        app._hd_cost_for_contract = lambda *args, **kwargs: {
            "qty": 100, "own_after": 9000, "local": 10000,
            "total_sav": 100000, "cif": 180, "fx": 50,
        }
        app._contract_pricing_lots = lambda c: c.get("pricing_lots", [])
        app._contract_cif_usd = lambda c: c.get("cif_usd_mt")
        app._contract_route_freight_rate = lambda c: None
        app._compute_stock_with_adjustments = lambda aliases: {
            alias: (500 if alias == "CORN" else 0, None) for alias in aliases}
        app.get_consumption_mt_day = lambda commodity: 50 if commodity == "CORN" else None
        app._home_commodity_options = lambda: ["CORN"]

        metrics = app._home_exec_metrics("CORN", fx_mode="live")
        self.assertEqual(metrics["realized_saving"], 200000)
        self.assertEqual(metrics["open_position"], 100000)
        self.assertEqual(metrics["realized_per_mt"], 1000)
        self.assertEqual(metrics["closed_qty"], 200)
        self.assertEqual(metrics["open_qty"], 100)
        self.assertEqual(metrics["unpriced_qty"], 60)
        self.assertEqual(metrics["open_value"], 900000)
        self.assertEqual(metrics["avg_contract"], 9000)
        self.assertEqual(metrics["avg_local"], 10000)
        self.assertEqual(metrics["coverage_days"], 12)
        self.assertEqual(metrics["data_gaps"], 0)

    def test_ceo_dashboard_declares_required_management_kpis(self):
        source = self.path.read_text(encoding="utf-8")
        for label in (
            "Realised Savings", "Saving / MT", "Closed Quantity",
            "Open Exposure", "Indicative Open", "Open Quantity",
            "Unpriced Quantity", "Avg Contract Cost", "Avg Local Market",
            "Lowest Coverage", "Data Gaps",
        ):
            self.assertIn(label, source)
        self.assertIn("Realised = closed only", source)
        self.assertIn("Indicative = open MTM", source)

    def test_basis_contract_price_egp_mt_uses_cif_times_contract_fx_only(self):
        app = self.module.App.__new__(self.module.App)
        price = app._basis_contract_price_egp_mt(416, 47.39)
        self.assertAlmostEqual(price, 19714.24, places=8)
        # This visible price excludes local fees; Own-After remains separate.
        self.assertAlmostEqual(price + 850, 20564.24, places=8)
        self.assertIsNone(app._basis_contract_price_egp_mt(416, None))

    def test_basis_contract_table_declares_visible_egp_price_column(self):
        source = self.path.read_text(encoding="utf-8")
        self.assertIn('("Contract EGP/MT", 135, "e")', source)
        self.assertIn('Contract EGP/MT = CIF USD/MT × contract FX used by Basis Tracker', source)

    def test_basis_workbook_keeps_auditable_formulas(self):
        app = self.module.App.__new__(self.module.App)
        app.state_obj = {"ui": {"basis_expenses_egp_mt": 850}}
        app._basis_reference_mode = lambda: ("PRICING", "Pricing Date")
        rows = [{
            "date": "2026-07-01", "kind": "CONTRACT", "contract": "C0001",
            "commodity": "CORN", "origin": "BRAZIL", "local_egp_mt": 12000,
            "expenses_egp_mt": 850, "fx": 50, "cbot": 440, "factor": 0.3937,
            "contract_basis": 25, "data_status": "Complete", "ref_mode": "Pricing Date",
        }]
        workbook = app._build_basis_excel_workbook(rows, "Savings Basis", "test filters")
        sheet = workbook["Basis Data"]
        self.assertEqual(sheet["A1"].value, "Savings Basis")
        self.assertTrue(str(sheet["N5"].value).startswith("=IF("))
        self.assertIn("M5-N5", str(sheet["O5"].value))

    def test_savings_basis_export_respects_visible_contract_ids(self):
        app = self.module.App.__new__(self.module.App)
        app._sv_current_filters = lambda: ("CORN", "Supplier A", "BRAZIL", "Closed")
        app._sv_collect_savings_rows = lambda *args: ([
            {"cid": "C0001", "commodity": "CORN"},
        ], {})
        app._basis_enriched_rows = lambda commodity, origin: [
            {"kind": "market", "commodity": commodity, "date": "2026-07-01"},
            {"kind": "CONTRACT", "contract_id": "C0001", "commodity": commodity},
            {"kind": "CONTRACT", "contract_id": "C9999", "commodity": commodity},
        ]
        captured = {}
        app._save_basis_rows_excel = lambda rows, *args: captured.update(rows=rows, args=args)
        app._surface_error = lambda *args, **kwargs: self.fail(str(args))
        app.export_savings_basis_excel()
        exported_contract_ids = {row.get("contract_id") for row in captured["rows"]
                                 if (row.get("kind") or "").upper() == "CONTRACT"}
        self.assertEqual(exported_contract_ids, {"C0001"})
        self.assertTrue(any((row.get("kind") or "").lower() == "market"
                            for row in captured["rows"]))



    def test_basis_tracker_has_sbm_contract_vs_local_excel_export(self):
        source = self.path.read_text(encoding="utf-8")
        self.assertIn("SBM vs Local Excel", source)
        self.assertIn("def export_sbm_vs_local_excel", source)
        self.assertIn("Delivery-Date FX EGP/USD", source)
        self.assertIn("Final prices use CIF ÷ 1.1023", source)
        self.assertIn("Local CBOT is excluded", source)
        self.assertIn("Equivalent Price Detail", source)

    def test_sbm_export_keeps_contract_fx_separate_from_delivery_market_fx(self):
        app = self.module.App.__new__(self.module.App)
        app.state_obj = {
            "ui": {"basis_expenses_egp_mt": 850, "basis_reference_mode": "Pricing Date"},
            "contracts": {
                "SCN1": {
                    "name": "SCN 1", "supplier": "NVO", "commodity": "SBM",
                    "origin": "LOCAL", "status": "Closed", "priced": True,
                    "pricing_type": "FLAT", "premium_cents": 0,
                    "qty_mt": 500, "cif_usd_mt": 400, "delivery_fx": 47.5,
                    "delivery_date": "2026-01-10", "storage_start": "2026-01-10",
                    "discharge_egp_mt": 0, "clearance_egp_mt": 0,
                    "freight_egp_mt": 0,
                }
            },
            "local_prices": [{
                "date": "2026-01-10", "commodity": "SBM",
                "price_egp_mt": 23000, "transport_egp_mt": 0,
            }],
            "cbot_history": [{
                "date": "2026-01-10", "commodity": "SBM", "close": 300,
            }],
            "fx_history": [{"date": "2026-01-10", "rate": 50.0}],
            "snapshots": [], "suppliers": {}, "market_data": {},
            "local_purchases": [],
        }
        rows, detail = app._collect_sbm_contract_vs_local_rows("ALL", "ALL")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["contract_fx"], 47.5)
        self.assertEqual(row["delivery_market_fx"], 50.0)
        self.assertAlmostEqual(row["contract_goods_egp_mt"], 19000.0)
        self.assertAlmostEqual(row["saving_egp_mt"], 4000.0)
        self.assertTrue(detail)

        workbook = app._build_sbm_contract_vs_local_workbook(rows, detail, "test")
        sheet = workbook["SBM vs Local"]
        self.assertEqual(sheet["L5"].value, 47.5)
        self.assertEqual(sheet["M5"].value, 50.0)
        self.assertIn("L5-M5", str(sheet["N5"].value))
        self.assertIn("K5*L5", str(sheet["O5"].value))
        self.assertIn("V5-S5", str(sheet["W5"].value))
        self.assertIn("Y5-Z5", str(sheet["AA5"].value))
        method = workbook["Method & Assumptions"]
        method_values = [cell.value for row in method.iter_rows() for cell in row]
        self.assertFalse(any(isinstance(value, str) and value.startswith("=")
                             for value in method_values))


    def test_home_contract_filter_matches_base_commodity(self):
        app = self.module.App.__new__(self.module.App)
        app._hd_sc_comm_var = type("Var", (), {"get": lambda self: "CORN"})()
        self.assertTrue(app._home_contract_matches_filter({"commodity": "CORN-BRZ"}))
        self.assertFalse(app._home_contract_matches_filter({"commodity": "SBM"}))
        self.assertTrue(app._home_contract_matches_filter({"commodity": "SBM"}, "All"))

    def test_clicking_commodity_refreshes_all_home_contract_panels(self):
        class Var:
            def __init__(self, value="All"): self.value = value
            def get(self): return self.value
            def set(self, value): self.value = value
        class Widget:
            def configure(self, **kwargs): self.kwargs = kwargs

        app = self.module.App.__new__(self.module.App)
        app._hd_sc_comm_var = Var()
        app._hd_sc_filter_btns = {"All": Widget(), "CORN": Widget()}
        app._hd_comm_kpi_vars = {"CORN": {"card": Widget()}, "SBM": {"card": Widget()}}
        calls = []
        for name in ("_refresh_hd_command_center", "_refresh_hd_mtm_daily_comparison",
                     "_refresh_hd_scorecard", "_refresh_hd_scenarios",
                     "_refresh_hd_provenance", "_refresh_hd_buy_signal"):
            setattr(app, name, lambda n=name: calls.append(n))
        app._home_select_commodity("CORN")
        self.assertEqual(app._hd_sc_comm_var.get(), "CORN")
        self.assertEqual(calls, [
            "_refresh_hd_command_center", "_refresh_hd_mtm_daily_comparison",
            "_refresh_hd_scorecard", "_refresh_hd_scenarios",
            "_refresh_hd_provenance", "_refresh_hd_buy_signal"])

    def test_realized_date_prefers_close_date_and_supports_legacy(self):
        app = self.module.App.__new__(self.module.App)
        current = app._contract_realized_date({
            "closed_date": "2026-07-20", "storage_end": "2026-06-30",
            "delivery_date": "2026-06-01"})
        legacy = app._contract_realized_date({
            "storage_end": "30-06-2026", "delivery_date": "2026-06-01"})
        self.assertEqual(current.isoformat(), "2026-07-20")
        self.assertEqual(legacy.isoformat(), "2026-06-30")

    def test_home_realized_kpis_ignore_hidden_savings_tab_filters(self):
        class Var:
            def __init__(self, value=""): self.value = value
            def get(self): return self.value
            def set(self, value): self.value = value
        class Tree:
            def __init__(self): self.rows = []
            def get_children(self): return []
            def delete(self, _iid): pass
            def insert(self, *args, **kwargs): self.rows.append((args, kwargs))

        app = self.module.App.__new__(self.module.App)
        app._hd_sc_comm_var = Var("CORN")
        app.hd_scorecard_tree = Tree()
        app.hd_kpi_month = Var()
        app.hd_kpi_saving = Var()
        app.hd_kpi_prev = Var()
        app.hd_saved_var = Var()
        app.state_obj = {"meta": {"saved_ts": "2026-07-25 10:00:00"}}
        app._refresh_home_commodity_cards = lambda: None
        app._refresh_home_executive_kpis = lambda month_total=None: None
        app._sv_current_filters = lambda: self.fail("Home must not inherit Savings-tab filters")
        captured = {}
        today = self.module.dt.date.today().isoformat()
        def collect(*args):
            captured["args"] = args
            return ([{
                "cid": "C1", "ref": "C1", "contract_status": "Closed",
                "origin": "BRAZIL", "qty": 100, "freight": 10,
                "own_after": 9000, "local": 9500, "sav_mt": 500,
                "total_sav": 50000, "realized_date": today,
                "delivery_date": "2026-06-01"}],
                {"grand_sav": 50000, "grand_qty": 100, "counted": 1})
        app._sv_collect_savings_rows = collect
        app._refresh_hd_scorecard()
        self.assertEqual(captured["args"], ("CORN", "All", "All", "Closed"))
        self.assertEqual(app.hd_kpi_saving.get(), "EGP 50,000")
        self.assertEqual(app.hd_kpi_prev.get(), "EGP 50,000")


    def test_flat_sbm_uses_delivery_date_in_pricing_view(self):
        app = self.module.App.__new__(self.module.App)
        app.state_obj = {
            "ui": {"basis_expenses_egp_mt": 850, "basis_reference_mode": "Pricing Date"},
            "local_prices": [
                {"date": "2026-06-01", "commodity": "SBM",
                 "price_egp_mt": 21000, "transport_egp_mt": 250},
                {"date": "2026-07-01", "commodity": "SBM",
                 "price_egp_mt": 22000, "transport_egp_mt": 250},
            ],
            "local_purchases": [],
            "contracts": {"C1": {
                "name": "NVO FLAT", "supplier": "NVO", "commodity": "SBM",
                "origin": "ARGENTINA", "status": "Closed", "qty_mt": 1000,
                "cif_usd_mt": 420,
                "pricing_date": "2026-06-01",
                "delivery_date": "2026-07-01",
                "delivery_fx": 47.25,
                "form4_fx": 60.00,
                "pricing_cbot": 280,
            }},
            "cbot_history": [
                {"date": "2026-06-01", "commodity": "SBM", "price": 280},
                {"date": "2026-07-01", "commodity": "SBM", "price": 300},
            ],
            "fx_history": [
                {"date": "2026-06-01", "rate": 49},
                {"date": "2026-07-01", "rate": 50},
            ],
            "snapshots": [],
        }
        rows = app._basis_enriched_rows("SBM", "ALL")
        contract = next(r for r in rows if r.get("kind") == "CONTRACT")
        expected_contract = 420 / self.module.SBM_ST_PER_MT
        expected_local = (22000 / 47.25) / self.module.SBM_ST_PER_MT
        self.assertEqual(contract["pricing_type"], "FLAT")
        self.assertEqual(contract["date"], "2026-07-01")
        self.assertEqual(contract["fx"], 47.25)
        self.assertEqual(contract["fx_source"], "contract SBM Pricing & Savings FX")
        self.assertEqual(contract["ref_mode"], "Delivery Date · final price")
        self.assertEqual(contract["comparison_metric"], "SBM_EQ_PRICE")
        self.assertAlmostEqual(contract["contract_basis"], expected_contract, places=8)
        self.assertAlmostEqual(contract["implied_basis"], expected_local, places=8)
        self.assertAlmostEqual(contract["spread"], expected_contract - expected_local, places=8)
        self.assertAlmostEqual(contract["contract_price_egp_mt"], 420 * 47.25, places=8)
        self.assertAlmostEqual(contract["own_after_egp_mt"], 420 * 47.25, places=8)
        self.assertEqual(contract["cbot_source"], "not used for final-price comparison")
        self.assertIn("local CBOT excluded", contract["data_status"])
        self.assertIn("final CIF price used", contract["data_status"])

    def test_flat_sbm_zero_placeholder_uses_delivery_date_without_pricing_warning(self):
        app = self.module.App.__new__(self.module.App)
        app.state_obj = {
            "ui": {"basis_expenses_egp_mt": 850, "basis_reference_mode": "Pricing Date"},
            "local_prices": [{"date": "2026-07-01", "commodity": "SBM",
                              "price_egp_mt": 22000, "transport_egp_mt": 250}],
            "local_purchases": [],
            "contracts": {"C1": {
                "name": "NVO LEGACY FLAT", "supplier": "NVO", "commodity": "SBM",
                "origin": "BRAZIL", "status": "Closed", "qty_mt": 1000,
                "cif_usd_mt": 420, "premium_cents": 0,
                "delivery_date": "2026-07-01", "delivery_fx": 47.25,
            }},
            "cbot_history": [{"date": "2026-07-01", "commodity": "SBM", "price": 300}],
            "fx_history": [{"date": "2026-07-01", "rate": 50}],
            "snapshots": [],
        }
        rows = app._basis_enriched_rows("SBM", "ALL")
        contract = next(r for r in rows if r.get("kind") == "CONTRACT")
        self.assertEqual(contract["pricing_type"], "FLAT")
        self.assertEqual(contract["date"], "2026-07-01")
        self.assertEqual(contract["ref_mode"], "Delivery Date · final price")
        self.assertNotIn("Missing Pricing Date", contract["data_status"])
        self.assertEqual(contract["cif_value_type"], "Final")
        self.assertEqual(contract["comparison_method"],
                         "FINAL PRICE = CIF USD/MT ÷ SBM conversion factor")

    def test_closed_zero_premium_sbm_with_final_price_uses_final_cif(self):
        app = self.module.App.__new__(self.module.App)
        app.state_obj = {
            "ui": {"basis_expenses_egp_mt": 850, "basis_reference_mode": "Pricing Date"},
            "local_prices": [{"date": "2026-07-01", "commodity": "SBM",
                              "price_egp_mt": 22000, "transport_egp_mt": 250}],
            "local_purchases": [],
            "contracts": {"C1": {
                "name": "NVO ZERO BASIS PREMIUM", "supplier": "NVO", "commodity": "SBM",
                "origin": "BRAZIL", "status": "Closed", "qty_mt": 1000,
                "pricing_type": "PREMIUM", "premium_cents": 0,
                "cif_usd_mt": 420, "delivery_date": "2026-07-01",
                "delivery_fx": 47.25,
            }},
            "cbot_history": [], "fx_history": [], "snapshots": [],
        }
        rows = app._basis_enriched_rows("SBM", "ALL")
        contract = next(r for r in rows if r.get("kind") == "CONTRACT")
        self.assertEqual(contract["pricing_type"], "PREMIUM")
        self.assertEqual(contract["date"], "2026-07-01")
        self.assertNotIn("Missing Pricing Date", contract["data_status"])
        self.assertEqual(contract["cif_value_type"], "Final")
        self.assertAlmostEqual(contract["contract_basis"],
                               420 / self.module.SBM_ST_PER_MT, places=8)

    def test_closed_premium_sbm_uses_final_price_and_delivery_date(self):
        app = self.module.App.__new__(self.module.App)
        app.state_obj = {
            "ui": {"basis_expenses_egp_mt": 850, "basis_reference_mode": "Pricing Date"},
            "local_prices": [
                {"date": "2026-06-01", "commodity": "SBM",
                 "price_egp_mt": 21000, "transport_egp_mt": 250},
                {"date": "2026-07-01", "commodity": "SBM",
                 "price_egp_mt": 22000, "transport_egp_mt": 250},
            ],
            "local_purchases": [],
            "contracts": {"C1": {
                "name": "NVO PREMIUM", "supplier": "NVO", "commodity": "SBM",
                "origin": "ARGENTINA", "status": "Closed", "qty_mt": 1000,
                "premium_cents": 45, "cif_usd_mt": 420,
                "pricing_date": "2026-06-01",
                "delivery_date": "2026-07-01",
                "delivery_fx": 48.75,
                "pricing_fx": 49.50,
                "form4_fx": 60.00,
            }},
            "cbot_history": [
                {"date": "2026-06-01", "commodity": "SBM", "price": 280},
                {"date": "2026-07-01", "commodity": "SBM", "price": 300},
            ],
            "fx_history": [
                {"date": "2026-06-01", "rate": 49},
                {"date": "2026-07-01", "rate": 50},
            ],
            "snapshots": [],
        }
        rows = app._basis_enriched_rows("SBM", "ALL")
        contract = next(r for r in rows if r.get("kind") == "CONTRACT")
        self.assertEqual(contract["pricing_type"], "PREMIUM")
        self.assertEqual(contract["date"], "2026-07-01")
        self.assertEqual(contract["ref_mode"], "Delivery Date · final price")
        self.assertAlmostEqual(contract["contract_basis"],
                               420 / self.module.SBM_ST_PER_MT, places=8)
        self.assertAlmostEqual(contract["implied_basis"],
                               (22000 / 48.75) / self.module.SBM_ST_PER_MT, places=8)
        self.assertEqual(contract["fx"], 48.75)
        self.assertEqual(contract["fx_source"], "contract SBM Pricing & Savings FX")
        self.assertEqual(contract["cbot_source"], "not used for final-price comparison")
        self.assertIn("final CIF price used", contract["data_status"])

    def test_sbm_missing_contract_fx_does_not_fall_back_to_history_or_form4(self):
        app = self.module.App.__new__(self.module.App)
        app.state_obj = {
            "ui": {"basis_expenses_egp_mt": 850, "basis_reference_mode": "Pricing Date"},
            "local_prices": [{"date": "2026-06-01", "commodity": "SBM",
                              "price_egp_mt": 21000, "transport_egp_mt": 250}],
            "local_purchases": [],
            "contracts": {"C1": {
                "name": "NVO PREMIUM", "supplier": "NVO", "commodity": "SBM",
                "origin": "ARGENTINA", "status": "Closed", "qty_mt": 1000,
                "premium_cents": 45, "pricing_date": "2026-06-01",
                "form4_fx": 60.0, "pricing_fx": 49.5,
            }},
            "cbot_history": [{"date": "2026-06-01", "commodity": "SBM", "price": 280}],
            "fx_history": [{"date": "2026-06-01", "rate": 49}],
            "snapshots": [{"contract_id": "C1", "ts": "2026-06-01 10:00:00", "fx": 50}],
        }
        rows = app._basis_enriched_rows("SBM", "ALL")
        contract = next(r for r in rows if r.get("kind") == "CONTRACT")
        self.assertIsNone(contract["fx"])
        self.assertEqual(contract["fx_source"], "missing contract SBM Pricing & Savings FX")
        self.assertIn("Missing SBM contract Pricing & Savings FX", contract["data_status"])
        self.assertNotIn("using nearest FX", contract["data_status"])

    def test_open_sbm_equivalent_price_uses_contract_stored_fx(self):
        app = self.module.App.__new__(self.module.App)
        app.state_obj = {
            "ui": {"basis_expenses_egp_mt": 850, "basis_reference_mode": "Pricing Date"},
            "local_prices": [{"date": "2026-07-01", "commodity": "SBM",
                              "price_egp_mt": 22000, "transport_egp_mt": 250}],
            "local_purchases": [],
            "contracts": {"C1": {
                "name": "NVO PREMIUM", "supplier": "NVO", "commodity": "SBM",
                "origin": "ARGENTINA", "status": "Open", "qty_mt": 1000,
                "premium_cents": 45, "delivery_fx": 47.0,
            }},
            "cbot_history": [{"date": "2026-07-01", "commodity": "SBM", "price": 300}],
            "fx_history": [{"date": "2026-07-01", "rate": 55}],
            "snapshots": [],
        }
        rows = app._basis_enriched_rows("SBM", "ALL")
        contract = next(r for r in rows if r.get("kind") == "CONTRACT")
        expected_local = (22000 / 47.0) / self.module.SBM_ST_PER_MT
        expected_contract = 300 + 45
        self.assertAlmostEqual(contract["current_local_basis"], expected_local, places=8)
        self.assertAlmostEqual(contract["current_contract_basis"], expected_contract, places=8)
        self.assertAlmostEqual(contract["current_spread"], expected_contract - expected_local, places=8)
        self.assertEqual(contract["current_market_fx"], 47.0)
        self.assertEqual(contract["current_market_fx_source"],
                         "contract SBM Pricing & Savings FX")
        self.assertAlmostEqual(contract["cif_usd_mt"],
                               expected_contract * self.module.SBM_ST_PER_MT, places=8)
        self.assertEqual(contract["cif_value_type"], "Estimated")

    def test_open_premium_contract_without_final_price_uses_cbot_plus_premium(self):
        app = self.module.App.__new__(self.module.App)
        app.state_obj = {
            "ui": {"basis_expenses_egp_mt": 850, "basis_reference_mode": "Pricing Date"},
            "local_prices": [{"date": "2026-07-01", "commodity": "SBM",
                              "price_egp_mt": 22000, "transport_egp_mt": 250}],
            "local_purchases": [],
            "contracts": {"C1": {
                "name": "NVO PREMIUM", "supplier": "NVO", "commodity": "SBM",
                "origin": "ARGENTINA", "status": "Open", "qty_mt": 1000,
                "premium_cents": 45,
                "delivery_fx": 48.0,
            }},
            "cbot_history": [{"date": "2026-07-01", "commodity": "SBM", "price": 300}],
            "fx_history": [{"date": "2026-07-01", "rate": 50}],
            "snapshots": [],
        }
        rows = app._basis_enriched_rows("SBM", "ALL")
        contract = next(r for r in rows if r.get("kind") == "CONTRACT")
        self.assertEqual(contract["date"], "2026-07-01")
        self.assertEqual(contract["plot_date"], "2026-07-01")
        self.assertEqual(contract["plot_basis"], 345)
        self.assertEqual(contract["contract_basis"], 345)
        self.assertEqual(contract["cif_value_type"], "Estimated")
        self.assertEqual(contract["cbot_source"],
                         "current CBOT used only for open premium estimate")
        self.assertIn("open premium uses current CBOT + premium", contract["data_status"])
        self.assertNotIn("Missing Pricing Date", contract["data_status"])

    def test_open_premium_with_saved_final_cif_switches_to_final_price_rule(self):
        app = self.module.App.__new__(self.module.App)
        app.state_obj = {
            "ui": {"basis_expenses_egp_mt": 850, "basis_reference_mode": "Pricing Date"},
            "local_prices": [{"date": "2026-07-01", "commodity": "SBM",
                              "price_egp_mt": 22000, "transport_egp_mt": 250}],
            "local_purchases": [],
            "contracts": {"C1": {
                "name": "NVO PREMIUM PRICED", "supplier": "NVO", "commodity": "SBM",
                "origin": "ARGENTINA", "status": "Open", "qty_mt": 1000,
                "premium_cents": 45, "cif_usd_mt": 420,
                "delivery_date": "2026-07-01", "delivery_fx": 48.0,
            }},
            "cbot_history": [{"date": "2026-07-01", "commodity": "SBM", "price": 300}],
            "fx_history": [{"date": "2026-07-01", "rate": 50}],
            "snapshots": [],
        }
        rows = app._basis_enriched_rows("SBM", "ALL")
        contract = next(r for r in rows if r.get("kind") == "CONTRACT")
        self.assertEqual(contract["cif_value_type"], "Final")
        self.assertAlmostEqual(contract["contract_basis"],
                               420 / self.module.SBM_ST_PER_MT, places=8)
        self.assertEqual(contract["cbot_source"], "not used for final-price comparison")
        self.assertEqual(contract["comparison_method"],
                         "FINAL PRICE = CIF USD/MT ÷ SBM conversion factor")

    def test_scn7860_like_final_price_is_favorable_against_equivalent_local_price(self):
        app = self.module.App.__new__(self.module.App)
        app.state_obj = {
            "ui": {"basis_expenses_egp_mt": 850, "basis_reference_mode": "Pricing Date"},
            "local_prices": [{"date": "2026-07-01", "commodity": "SBM",
                              "price_egp_mt": 33700, "transport_egp_mt": 400}],
            "local_purchases": [],
            "contracts": {"C1": {
                "name": "SCN 7860", "supplier": "NVO", "commodity": "SBM",
                "origin": "ARGENTINA", "status": "Closed", "qty_mt": 500,
                "pricing_type": "PREMIUM", "premium_cents": 104,
                "cif_usd_mt": 460.65, "delivery_date": "2026-07-01",
                "delivery_fx": 54.45, "freight_egp_mt": 252.37,
            }},
            "cbot_history": [{"date": "2026-07-01", "commodity": "SBM", "price": 316}],
            "fx_history": [{"date": "2026-07-01", "rate": 55}],
            "snapshots": [],
        }
        rows = app._basis_enriched_rows("SBM", "ALL")
        contract = next(r for r in rows if r.get("kind") == "CONTRACT")
        expected_contract = 460.65 / self.module.SBM_ST_PER_MT
        expected_local = (33700 / 54.45) / self.module.SBM_ST_PER_MT
        self.assertAlmostEqual(contract["contract_basis"], expected_contract, places=8)
        self.assertAlmostEqual(contract["implied_basis"], expected_local, places=8)
        self.assertLess(contract["spread"], 0)
        self.assertAlmostEqual(contract["saving_egp_mt"],
                               34100 - (460.65 * 54.45 + 252.37), places=6)
        self.assertIn("Cheaper than local", app._basis_contract_display_status(contract))

    def test_open_status_filter_keeps_local_market_context(self):
        class Var:
            def __init__(self, value): self.value = value
            def get(self): return self.value
        app = self.module.App.__new__(self.module.App)
        app.basis_search_var = Var("")
        app.basis_status_var = Var("Open")
        app.basis_row_view_var = Var("Both")
        app.basis_missing_only_var = Var(False)
        app.basis_date_range_var = Var("All")
        rows = [
            {"kind": "MARKET", "date": "2026-07-01"},
            {"kind": "CONTRACT", "contract_status": "Open", "date": "2026-07-01"},
            {"kind": "CONTRACT", "contract_status": "Closed", "date": "2026-07-01"},
        ]
        filtered = app._basis_apply_accessibility_filters(rows)
        self.assertEqual([r["kind"] for r in filtered], ["MARKET", "CONTRACT"])

    def test_open_contract_status_reports_up_or_down_vs_local(self):
        app = self.module.App.__new__(self.module.App)
        below = app._basis_contract_display_status({
            "kind": "CONTRACT", "contract_status": "Open",
            "current_spread": -10, "data_status": "Complete"})
        above = app._basis_contract_display_status({
            "kind": "CONTRACT", "contract_status": "Open",
            "current_spread": 10, "data_status": "Complete"})
        self.assertIn("below local", below)
        self.assertIn("above local", above)


    def test_sbm_spreadsheet_date_mapping_has_80_unique_contracts(self):
        self.assertEqual(len(self.module.SBM_CONTRACT_DELIVERY_DATES), 80)
        self.assertEqual(self.module.SBM_CONTRACT_DELIVERY_DATES["SCN 7314"],
                         "2026-01-05")
        self.assertEqual(self.module.SBM_CONTRACT_DELIVERY_DATES["SCN 8392"],
                         "2026-07-13")

    def test_sbm_date_sync_updates_delivery_and_storage_start_only_once(self):
        state = {
            "meta": {}, "data_issues": [], "audit_log": [],
            "contracts": {
                "C1": {
                    "name": "NVO / SCN-7314 / SBM", "commodity": "SBM",
                    "delivery_date": "2026-02-01",
                    "storage_start": "2026-02-02",
                    "storage_end": "2026-02-10",
                },
                "C2": {
                    "name": "SCN 7314", "commodity": "CORN",
                    "delivery_date": "2026-09-01",
                    "storage_start": "2026-09-01",
                },
            },
        }
        first = self.module.apply_sbm_contract_delivery_storage_dates(state)
        self.assertEqual(first["updated"], 1)
        self.assertEqual(state["contracts"]["C1"]["delivery_date"], "2026-01-05")
        self.assertEqual(state["contracts"]["C1"]["storage_start"], "2026-01-05")
        self.assertEqual(state["contracts"]["C1"]["storage_end"], "2026-02-10")
        self.assertEqual(state["contracts"]["C2"]["delivery_date"], "2026-09-01")

        # A manual edit after migration must not be overwritten at next startup.
        state["contracts"]["C1"]["delivery_date"] = "2026-01-06"
        state["contracts"]["C1"]["storage_start"] = "2026-01-06"
        second = self.module.apply_sbm_contract_delivery_storage_dates(state)
        self.assertEqual(second["updated"], 0)
        self.assertEqual(second["already_processed"], 1)
        self.assertEqual(state["contracts"]["C1"]["delivery_date"], "2026-01-06")


    def test_contracts_default_order_is_delivery_date_newest_first(self):
        class DummyVar:
            def get(self):
                return "Delivery Date · Newest First"
        app = self.module.App.__new__(self.module.App)
        app.contract_sort_var = DummyVar()
        items = app._contracts_table_items({
            "C1": {"delivery_date": "2026-01-05"},
            "C3": {"delivery_date": "2026-03-01"},
            "C2": {"delivery_date": "2026-02-10"},
            "C9": {},
        })
        self.assertEqual([cid for cid, _ in items], ["C3", "C2", "C1", "C9"])

    def test_contracts_tab_exposes_delivery_export_and_compare_actions(self):
        source = self.path.read_text(encoding="utf-8")
        self.assertIn('"DeliveryDate": "Delivery Date"', source)
        self.assertIn('Delivery Date · Newest First', source)
        self.assertIn('Export Visible', source)
        self.assertIn('def _export_contracts_excel', source)
        self.assertIn('def _open_contract_comparison', source)
        self.assertIn('Compare Two Contracts', source)

    def test_contract_export_workbook_has_contracts_summary_and_lots(self):
        app = self.module.App.__new__(self.module.App)
        app.state_obj = {"contracts": {}, "local_prices": [], "snapshots": [], "suppliers": {}, "commodities": {}, "consumption": {}, "market_data": {}}
        app._hd_cost_for_contract = lambda cid, c, **kwargs: {
            "cif": c.get("cif_usd_mt"), "fx": c.get("delivery_fx"),
            "disc": 0, "clr": 0, "freight": c.get("freight_egp_mt", 0),
            "own_after": 10100, "local": 11000, "local_date": "2026-02-01",
            "sav_mt": 900, "total_sav": 900000,
        }
        app._calc_contract_balance_row = lambda cid, c: {"RemainingMT": c.get("qty_mt")}
        app._contract_pricing_lots = lambda c: c.get("pricing_lots", [])
        app._contract_cif_usd = lambda c, cid=None: c.get("cif_usd_mt")
        items = [("C2", {"name": "Second", "delivery_date": "2026-02-01", "status": "Closed", "commodity": "CORN", "qty_mt": 1000, "cif_usd_mt": 200, "delivery_fx": 50, "freight_egp_mt": 100,
                          "pricing_lots": [{"date": "2026-01-20", "qty_mt": 1000, "premium_cents": 25}]})]
        wb, rows = app._build_contracts_workbook(items, "Test")
        self.assertEqual(wb.sheetnames, ["Summary", "Contracts", "Pricing Lots"])
        self.assertEqual(rows[0]["contract_id"], "C2")
        self.assertEqual(wb["Contracts"]["A5"].value, "2026-02-01")
        self.assertEqual(wb["Pricing Lots"]["A2"].value, "C2")

    def test_previous_dashboard_version_is_preserved_for_contract_upgrade(self):
        self.assertTrue((self.project / "legacy" / "V10_8_14_Frozen.py").exists())

    def test_daily_fifo_and_scenario_lab_are_present(self):
        source = self.path.read_text(encoding="utf-8")
        self.assertIn("Current FIFO Inventory", source)
        self.assertIn("def _fifo_portfolio", source)
        self.assertIn("fifo_inventory_daily", source)
        self.assertIn("Scenario Lab", source)
        self.assertIn("inventory_auto_estimate_daily", source)

    def test_freight_vat_modes_are_explicit(self):
        source = self.path.read_text(encoding="utf-8")
        self.assertIn("DETAILED = base × (1+VAT)", source)
        self.assertIn("ALL_IN = final/average freight", source)
        self.assertIn("freight_base_egp_mt", source)


if __name__ == "__main__":
    unittest.main()

"""Regression tests for the Aurora modern interface.

Split in two: everything that can be checked without a display (tokens,
contrast, drawing geometry, and the whole CBOT feed) runs everywhere; the
widget/screen smoke tests skip themselves when Tk cannot open a display, so
the suite still passes on a headless build machine.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import pathlib
import sys
import unittest

PROJECT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from prometheus_ui import primitives as pr
from prometheus_ui import theme as th
from prometheus_ui.cbot_console import CBOTFeed, RANGES, TRACKED_COMMODITIES


def _tk_available():
    try:
        import tkinter as tk
        root = tk.Tk()
        root.destroy()
        return True
    except Exception:
        return False


HAS_DISPLAY = _tk_available()
TODAY = dt.date(2026, 9, 8)


def _state():
    """A small state dict shaped exactly like the app's app_state.json."""
    cbot, fx, local = [], [], []
    for i in range(120, -1, -1):
        day = (TODAY - dt.timedelta(days=i)).isoformat()
        cbot.append({"date": day, "commodity": "CORN", "price": 400.0 + i * 0.5,
                     "source": "yahoo"})
        cbot.append({"date": day, "commodity": "SBM", "close": 300.0 - i * 0.2,
                     "source": "yahoo"})
        fx.append({"date": day, "rate": 48.0 + i * 0.01})
    for i in (0, 10, 20):
        local.append({"date": (TODAY - dt.timedelta(days=i)).isoformat(),
                      "commodity": "CORN", "price_egp_mt": 24000 + i,
                      "transport_egp_mt": 400})
    return {
        "market_data": {
            "cbot_quotes": {"CORN": 460.0, "SBM": {"price": 305.0}},
            "cbot_ts": TODAY.isoformat(),
            "fx": {"price": 49.25, "fetched_at": TODAY.isoformat()},
        },
        "cbot_history": cbot,
        "fx_history": fx,
        "local_prices": local,
        "contracts": {
            "C1": {"name": "C1", "commodity": "CORN", "status": "Open",
                   "qty_mt": 10000, "priced": False, "cif_usd_mt": None,
                   "premium_cents": 200.0, "supplier": "Cargill",
                   "delivery_date": (TODAY + dt.timedelta(days=5)).isoformat()},
            "C2": {"name": "C2", "commodity": "CORN", "status": "Open",
                   "qty_mt": 6000, "priced": True, "cif_usd_mt": 285.0,
                   "premium_cents": 190.0, "form4_fx": 49.0,
                   "delivery_date": (TODAY + dt.timedelta(days=60)).isoformat()},
            "C3": {"name": "C3", "commodity": "SBM", "status": "Open",
                   "qty_mt": 4000, "priced": False, "cif_usd_mt": None,
                   "premium_cents": 0.0,
                   "delivery_date": (TODAY + dt.timedelta(days=90)).isoformat()},
            "C4": {"name": "C4", "commodity": "CORN", "status": "Closed",
                   "qty_mt": 9000, "priced": True, "cif_usd_mt": 270.0},
        },
    }


class ThemeTokenTests(unittest.TestCase):
    def test_both_palettes_expose_the_same_tokens(self):
        day, night = th.PALETTES["day"], th.PALETTES["night"]
        self.assertEqual(set(day), set(night))

    def test_text_tones_clear_wcag_aa_on_their_own_ground(self):
        for name in ("day", "night"):
            theme = th.theme_for(name)
            for token in ("ink", "ink_2", "ink_3"):
                self.assertGreaterEqual(
                    th.contrast_ratio(theme.c(token), theme.c("surface")), 4.5,
                    f"{name}/{token} is unreadable on the card surface")
            for tone in ("mint", "amber", "rose", "sky", "violet", "brand"):
                self.assertGreaterEqual(
                    th.contrast_ratio(theme.tone_ink(tone), theme.soft(tone)), 4.5,
                    f"{name}/{tone} chip text is unreadable on its own tint")
                self.assertGreaterEqual(
                    th.contrast_ratio(theme.on_tone(tone), theme.c(tone)), 4.5,
                    f"{name}/{tone} solid fill cannot carry a readable label")
            self.assertGreaterEqual(
                th.contrast_ratio(theme.c("rail_ink_soft"), theme.c("rail")), 4.5,
                f"{name} rail section labels are unreadable")

    def test_font_scale_is_clamped_and_applied(self):
        self.assertEqual(th.theme_for("day", font_scale=0.1).font_scale, 0.8)
        self.assertEqual(th.theme_for("day", font_scale=9.0).font_scale, 1.6)
        big = th.theme_for("day", font_scale=1.4)
        self.assertGreater(big.size("title"), th.theme_for("day").size("title"))

    def test_delta_tone_reads_direction_not_sign(self):
        theme = th.theme_for("day")
        self.assertEqual(theme.delta_tone(5, positive_is_good=True), "mint")
        self.assertEqual(theme.delta_tone(5, positive_is_good=False), "rose")
        self.assertEqual(theme.delta_tone(None), "sky")

    def test_unknown_colour_token_raises_rather_than_guessing(self):
        with self.assertRaises(KeyError):
            th.theme_for("day").c("not_a_token")

    def test_literal_hex_passes_through(self):
        self.assertEqual(th.theme_for("day").c("#123456"), "#123456")


class PrimitiveGeometryTests(unittest.TestCase):
    def test_rounded_rect_repeats_corner_points_for_the_spline(self):
        pts = pr.round_rect_points(0, 0, 100, 60, 12)
        self.assertEqual(len(pts) % 2, 0)
        self.assertGreaterEqual(len(pts), 32)

    def test_radius_is_clamped_to_the_shape(self):
        pts = pr.round_rect_points(0, 0, 10, 10, 999)
        self.assertTrue(all(0 <= v <= 10 for v in pts))

    def test_gradient_scanline_inset_follows_the_corner_circle(self):
        # At the very top the inset is the full radius; at the middle, zero.
        self.assertAlmostEqual(pr.inset_for_row(0, 0, 50, 12), 12.0, places=6)
        self.assertAlmostEqual(pr.inset_for_row(25, 0, 50, 12), 0.0, places=6)
        self.assertAlmostEqual(pr.inset_for_row(50, 0, 50, 12), 12.0, places=6)
        self.assertGreater(pr.inset_for_row(3, 0, 50, 12),
                           pr.inset_for_row(8, 0, 50, 12))

    def test_smoothing_keeps_the_endpoints(self):
        raw = [(0, 0), (1, 5), (2, 2), (3, 8)]
        out = pr.smooth_path(raw)
        self.assertEqual((out[0], out[1]), (0.0, 0.0))
        self.assertEqual((out[-2], out[-1]), (3.0, 8.0))
        self.assertGreater(len(out) // 2, len(raw))

    def test_colour_mixing_is_bounded(self):
        self.assertEqual(th.mix("#000000", "#ffffff", 0.0), "#000000")
        self.assertEqual(th.mix("#000000", "#ffffff", 1.0), "#ffffff")
        self.assertEqual(th.mix("#000000", "#ffffff", 5.0), "#ffffff")


class CBOTFeedTests(unittest.TestCase):
    def setUp(self):
        self.feed = CBOTFeed(_state(), today=TODAY)

    def test_quote_reads_both_stored_shapes(self):
        self.assertEqual(self.feed.quote("CORN")[0], 460.0)
        self.assertEqual(self.feed.quote("SBM")[0], 305.0)

    def test_quote_falls_back_to_history_when_no_live_quote(self):
        feed = CBOTFeed({**_state(), "market_data": {}}, today=TODAY)
        price, stamp = feed.quote("CORN")
        self.assertEqual(price, 400.0)
        self.assertEqual(stamp, TODAY.isoformat())

    def test_history_windows_and_dedupes(self):
        self.assertEqual(len(self.feed.history("CORN", 30)), 31)
        self.assertEqual(len(self.feed.history("CORN")), 121)
        dupes = _state()
        dupes["cbot_history"].append(
            {"date": TODAY.isoformat(), "commodity": "CORN", "price": 999.0})
        feed = CBOTFeed(dupes, today=TODAY)
        series = feed.history("CORN")
        self.assertEqual(len(series), 121)
        self.assertEqual(series[-1][1], 999.0)

    def test_history_uses_close_when_price_is_absent(self):
        self.assertTrue(self.feed.history("SBM"))

    def test_origin_suffixes_resolve_to_the_base_board(self):
        self.assertEqual(self.feed.history("CORN-BRZ"), self.feed.history("CORN"))

    def test_change_and_band(self):
        self.assertLess(self.feed.change("CORN", 30), 0)   # series falls to today
        low, high = self.feed.band("CORN", 365)
        self.assertEqual(low, 400.0)
        self.assertEqual(high, 460.0)

    def test_change_needs_two_points(self):
        feed = CBOTFeed({"cbot_history": [
            {"date": TODAY.isoformat(), "commodity": "CORN", "price": 1.0}]},
            today=TODAY)
        self.assertIsNone(feed.change("CORN", 30))

    def test_weighted_premium_ignores_closed_and_zero_premiums(self):
        # C1 (10000 @ 200) and C2 (6000 @ 190) are open; C3's premium is 0
        # (untracked, not a real zero basis) and C4 is closed.
        self.assertAlmostEqual(self.feed.weighted_premium("CORN"),
                               (200 * 10000 + 190 * 6000) / 16000, places=6)
        self.assertIsNone(self.feed.weighted_premium("SBM"))

    def test_implied_usd_uses_the_core_conversion_factor(self):
        value, note = self.feed.implied_usd_mt("CORN", premium=200.0)
        self.assertAlmostEqual(value, (460.0 + 200.0) * 0.3937, places=6)
        self.assertIn("200", note)

    def test_missing_premium_is_never_silently_zero(self):
        value, note = self.feed.implied_usd_mt("SBM")
        self.assertAlmostEqual(value, 305.0 * 1.1023, places=6)
        self.assertIn("zero basis", note)

    def test_no_quote_yields_no_number_at_all(self):
        feed = CBOTFeed({"contracts": {}}, today=TODAY)
        value, note = feed.implied_usd_mt("CORN")
        self.assertIsNone(value)
        self.assertIn("no board quote", note)

    def test_replacement_needs_fx(self):
        state = _state()
        state["market_data"]["fx"] = {}
        state["fx_history"] = []
        value, note = CBOTFeed(state, today=TODAY).replacement_egp_mt("CORN")
        self.assertIsNone(value)
        self.assertIn("FX", note)

    def test_replacement_uses_todays_fx(self):
        value, _note = self.feed.replacement_egp_mt("CORN", premium=200.0)
        self.assertAlmostEqual(value, (460.0 + 200.0) * 0.3937 * 49.25, places=4)

    def test_local_all_in_adds_transport_and_takes_the_latest_date(self):
        value, date = self.feed.local_all_in("CORN")
        self.assertEqual(value, 24400.0)
        self.assertEqual(date, TODAY.isoformat())
        self.assertEqual(self.feed.local_all_in("WHEAT"), (None, ""))

    def test_exposure_splits_priced_and_ignores_closed(self):
        exposure = self.feed.exposure("CORN")
        self.assertEqual(exposure["contracts"], 2)
        self.assertEqual(exposure["open_mt"], 16000)
        self.assertEqual(exposure["priced_mt"], 6000)
        self.assertEqual(exposure["unpriced_mt"], 10000)

    def test_exposure_counts_fx_unsecured_value_only(self):
        # Only C2 carries a Form 4; C1/C3 have no CIF so contribute no value.
        self.assertEqual(self.feed.exposure()["fx_unsecured_usd"], 0.0)
        state = _state()
        state["contracts"]["C1"]["cif_usd_mt"] = 290.0
        feed = CBOTFeed(state, today=TODAY)
        self.assertEqual(feed.exposure("CORN")["fx_unsecured_usd"], 10000 * 290.0)

    def test_exposure_rows_lead_with_unpriced_nearest_delivery(self):
        rows = self.feed.exposure()["rows"]
        self.assertFalse(rows[0]["priced"])
        self.assertEqual(rows[0]["id"], "C1")
        self.assertEqual(rows[0]["days_out"], 5)

    def test_coverage_fraction_is_none_without_an_open_book(self):
        self.assertIsNone(CBOTFeed({"contracts": {}}, today=TODAY).coverage_fraction())
        self.assertAlmostEqual(self.feed.coverage_fraction(self.feed.exposure("CORN")),
                               6000 / 16000)

    def test_signals_flag_unpriced_tons_inside_the_alert_window(self):
        titles = [t for _tone, t, _d in self.feed.signals("CORN")]
        self.assertTrue(any("unpriced inside" in t for t in titles))

    def test_signals_flag_a_stale_board_quote(self):
        state = _state()
        state["market_data"]["cbot_ts"] = "2026-01-01"
        titles = [t for _tone, t, _d in CBOTFeed(state, today=TODAY).signals("CORN")]
        self.assertIn("Board quote is stale", titles)

    def test_signals_say_when_a_missing_premium_makes_replacement_flat(self):
        titles = [t for _tone, t, _d in self.feed.signals("SBM")]
        self.assertTrue(any("defensible premium" in t for t in titles))

    def test_signals_never_return_empty(self):
        clean = {
            "market_data": {"cbot_quotes": {"CORN": 450.0},
                            "cbot_ts": TODAY.isoformat(),
                            "fx": {"price": 49.0}},
            "cbot_history": [{"date": TODAY.isoformat(), "commodity": "CORN",
                              "price": 450.0}],
            "contracts": {"X": {"commodity": "CORN", "status": "Open",
                                "qty_mt": 100, "priced": True,
                                "cif_usd_mt": 280.0, "premium_cents": 150.0,
                                "form4_fx": 49.0}},
        }
        signals = CBOTFeed(clean, today=TODAY).signals("CORN")
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0][0], "mint")

    def test_feed_never_mutates_the_state_it_reads(self):
        state = _state()
        before = repr(state)
        feed = CBOTFeed(state, today=TODAY)
        feed.signals("CORN")
        feed.exposure()
        feed.spark("CORN", 90)
        self.assertEqual(repr(state), before)


@unittest.skipUnless(HAS_DISPLAY, "no Tk display available")
class WidgetSmokeTests(unittest.TestCase):
    """Every widget must build, paint and resize without raising."""

    @classmethod
    def setUpClass(cls):
        import tkinter as tk
        cls.tk = tk

    def _root(self, palette="day"):
        root = self.tk.Tk()
        root.geometry("1200x800")
        self.addCleanup(root.destroy)
        return root, th.theme_for(palette)

    def test_widget_kit_paints_in_both_palettes(self):
        from prometheus_ui import apply_ttk_skin, charts as C, widgets as W
        for palette in ("day", "night"):
            root, theme = self._root(palette)
            self.assertTrue(apply_ttk_skin(root, theme))
            root.configure(bg=theme.c("bg"))
            hero = W.HeroBanner(root, theme)
            hero.pack(fill="x")
            hero.set_content(eyebrow="cbot", headline="Board", support="x",
                             metric_label="CORN", metric_value="452.25",
                             metric_delta="-1.2%", footnote="now")
            hero.set_actions([("Go", lambda: None)])
            tile = W.StatTile(root, theme, caption="c", value="1", glyph="◆")
            tile.pack()
            tile.set(value="2", delta="+1%", delta_tone="mint", spark=[1, 2, 3])
            W.PillButton(root, theme, "Go", variant="ghost").pack()
            W.SegmentedControl(root, theme, ["A", "B"]).pack()
            W.ToggleSwitch(root, theme).pack()
            W.SearchField(root, theme).pack()
            W.Chip(root, theme, "Open", tone="mint").pack()
            W.MetricRow(root, theme, "l", "v", tone="sky").pack()
            row = W.ListRow(root, theme)
            row.pack()
            row.set(title="t", subtitle="s", value="1 MT", chip="Unpriced",
                    chip_tone="amber")
            W.EmptyState(root, theme, title="none").pack()
            track = W.ProgressTrack(root, theme)
            track.pack(fill="x")
            track.set_segments([(0.4, "mint"), (0.6, "amber")])
            chart = C.AreaChart(root, theme)
            chart.pack(fill="both", expand=True)
            chart.set_series([(str(i), i * 1.5) for i in range(20)])
            bars = C.BarChart(root, theme)
            bars.pack(fill="x")
            bars.set_bars([("A", 3), ("B", -1)])
            gauge = C.DonutGauge(root, theme)
            gauge.pack()
            gauge.set([(0.5, "mint")], "50%", "priced")
            meter = C.RangeMeter(root, theme)
            meter.pack(fill="x")
            meter.set(1, 10, 5)
            root.update_idletasks()
            root.update()

    def test_charts_report_missing_data_instead_of_drawing_nothing(self):
        from prometheus_ui import charts as C
        root, theme = self._root()
        chart = C.AreaChart(root, theme)
        chart.pack(fill="both", expand=True)
        chart.set_series([])
        root.update_idletasks()
        root.update()
        texts = [chart.itemcget(i, "text") for i in chart.find_all()
                 if chart.type(i) == "text"]
        self.assertTrue(any("history" in t for t in texts))

    def test_search_field_placeholder_is_not_a_value(self):
        from prometheus_ui import widgets as W
        root, theme = self._root()
        field = W.SearchField(root, theme, placeholder="Search")
        field.pack()
        root.update_idletasks()
        self.assertEqual(field.get(), "")
        field._on_focus_in()
        field.var.set("corn")
        self.assertEqual(field.get(), "corn")

    def test_segmented_control_reports_the_chosen_value(self):
        from prometheus_ui import widgets as W
        chosen = []
        root, theme = self._root()
        seg = W.SegmentedControl(root, theme, ["30D", "90D"],
                                 command=chosen.append)
        seg.pack()
        seg.set_value("90D", notify=True)
        self.assertEqual(seg.value, "90D")
        self.assertEqual(chosen, ["90D"])


@unittest.skipUnless(HAS_DISPLAY, "no Tk display available")
class ShellAndConsoleTests(unittest.TestCase):
    def _root(self):
        import tkinter as tk
        root = tk.Tk()
        root.geometry("1400x900")
        self.addCleanup(root.destroy)
        return root, th.theme_for("day")

    def test_shell_navigates_and_tracks_the_active_destination(self):
        from prometheus_ui.shell import ModernShell
        seen = []
        root, theme = self._root()
        dests = [{"key": "a", "label": "Alpha", "glyph": "◆", "section": "S"},
                 {"key": "b", "label": "Beta", "glyph": "●", "section": "S"}]
        shell = ModernShell(root, theme, dests, on_navigate=seen.append)
        shell.pack(fill="both", expand=True)
        shell.select("b")
        root.update_idletasks()
        self.assertEqual(shell.sidebar.active, "b")
        self.assertEqual(shell.topbar.title_var.get(), "Beta")
        shell.sidebar._items["a"]._on_click()
        self.assertEqual(seen, ["a"])
        shell.toggle_rail()
        root.update_idletasks()

    def test_shell_chips_can_be_set_and_removed(self):
        from prometheus_ui.shell import ModernShell
        root, theme = self._root()
        shell = ModernShell(root, theme, [{"key": "a", "label": "A"}])
        shell.pack(fill="both", expand=True)
        shell.topbar.set_chip("fx", "FX 49.0", "sky")
        shell.topbar.set_chip("fx", "FX 49.5", "mint")
        self.assertEqual(shell.topbar._chip_cache["fx"]._text, "FX 49.5")
        shell.topbar.remove_chip("fx")
        self.assertNotIn("fx", shell.topbar._chip_cache)

    def test_command_palette_filters_and_chooses(self):
        from prometheus_ui.shell import ModernShell
        root, theme = self._root()
        shell = ModernShell(root, theme,
                            [{"key": "a", "label": "Alpha"},
                             {"key": "b", "label": "Beta"}])
        shell.pack(fill="both", expand=True)
        root.update_idletasks()
        palette = shell.open_palette([])
        self.addCleanup(lambda: palette.winfo_exists() and palette.destroy())
        palette._on_query("bet")
        self.assertEqual([e["label"] for e in palette._filtered], ["Beta"])
        palette._on_query("")
        self.assertEqual(len(palette._filtered), 2)

    def test_console_renders_and_survives_every_commodity_and_range(self):
        from prometheus_ui.cbot_console import CBOTCommandCenter
        root, theme = self._root()
        console = CBOTCommandCenter(root, theme, CBOTFeed(_state(), today=TODAY))
        console.pack(fill="both", expand=True)
        console.refresh()
        for commodity in TRACKED_COMMODITIES:
            console._on_commodity(commodity)
            for window in RANGES:
                console._on_range(window)
            root.update_idletasks()
        self.assertEqual(console._commodity, TRACKED_COMMODITIES[-1])

    def test_console_renders_against_an_empty_state(self):
        from prometheus_ui.cbot_console import CBOTCommandCenter
        root, theme = self._root()
        console = CBOTCommandCenter(root, theme, CBOTFeed({}, today=TODAY))
        console.pack(fill="both", expand=True)
        console.refresh()
        root.update_idletasks()
        self.assertEqual(console.tiles["board"].value_var.get(), "—")

    def test_console_actions_are_wired_to_the_host(self):
        from prometheus_ui.cbot_console import CBOTCommandCenter
        fired = []
        root, theme = self._root()
        console = CBOTCommandCenter(
            root, theme, CBOTFeed(_state(), today=TODAY),
            actions={"refresh_quotes": lambda: fired.append("refresh")})
        console.pack(fill="both", expand=True)
        console.refresh()
        root.update_idletasks()
        console.hero._actions[0][1]()
        self.assertEqual(fired, ["refresh"])


class DesktopIntegrationTests(unittest.TestCase):
    """Source-level guarantees about how the app wires the modern shell."""

    @classmethod
    def setUpClass(cls):
        cls.path = PROJECT / "Prometheus_V10_9_2.py"
        cls.source = cls.path.read_text(encoding="utf-8")
        spec = importlib.util.spec_from_file_location(
            "prometheus_desktop_modern_ui", cls.path)
        cls.module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(cls.module)

    def test_the_kit_is_imported_defensively(self):
        self.assertIn("HAS_MODERN_UI", self.source)
        self.assertTrue(self.module.HAS_MODERN_UI)

    def test_every_rail_destination_names_a_real_tab_attribute(self):
        for dest in self.module.MODERN_DESTINATIONS:
            for key in ("key", "tab", "label", "glyph", "section"):
                self.assertIn(key, dest)
            self.assertTrue(dest["tab"].startswith("tab_"))
        keys = [d["key"] for d in self.module.MODERN_DESTINATIONS]
        self.assertEqual(keys[0], "cbot", "the CBOT desk leads the rail")
        self.assertEqual(len(keys), len(set(keys)))

    def test_navigation_is_widget_identity_based_not_index_based(self):
        self.assertIn("self.nb.select(widget)", self.source)
        self.assertNotIn("self.nb.select(0)", self.source)

    def test_the_classic_chrome_is_still_reachable(self):
        self.assertIn("modern_interface", self.source)
        self.assertIn("def _modern_ui_enabled", self.source)
        self.assertIn("Apply Appearance", self.source)

    def test_rebuild_clears_dead_widget_references_first(self):
        rebuild = self.source[self.source.index("def _rebuild_interface"):]
        rebuild = rebuild[:rebuild.index("# ── CBOT Command Center")]
        self.assertIn("_drop_dead_widget_refs", rebuild)
        self.assertLess(rebuild.index("_drop_dead_widget_refs"),
                        rebuild.index("self._build_top_bar()"))

    def test_cbot_console_is_built_and_refreshed(self):
        self.assertIn("def _build_cbot_console", self.source)
        self.assertIn("def refresh_cbot_console", self.source)
        self.assertIn("refresh_all→refresh_cbot_console", self.source)


if __name__ == "__main__":
    unittest.main()

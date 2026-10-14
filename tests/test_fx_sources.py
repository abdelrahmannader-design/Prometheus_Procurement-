"""Bank rate parsing: the shapes a published rate page actually comes in."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prometheus_core.fx_sources import parse_bank_rates, pick_costing_rate


class ParseTests(unittest.TestCase):
    def test_plain_rate_table(self):
        html = """<table>
          <tr><th>Currency</th><th>Buy</th><th>Sell</th></tr>
          <tr><td>US Dollar</td><td>47.2500</td><td>47.3500</td></tr>
          <tr><td>Euro</td><td>55.1000</td><td>55.3000</td></tr>
        </table>"""
        found = parse_bank_rates(html)
        self.assertAlmostEqual(found["buy"], 47.25)
        self.assertAlmostEqual(found["sell"], 47.35)

    def test_currency_code_instead_of_a_name(self):
        html = "<tr><td>USD</td><td>47.10</td><td>47.40</td></tr>"
        self.assertAlmostEqual(parse_bank_rates(html)["sell"], 47.40)

    def test_arabic_row(self):
        html = "<tr><td>دولار امريكي</td><td>47.10</td><td>47.40</td></tr>"
        self.assertAlmostEqual(parse_bank_rates(html)["sell"], 47.40)

    def test_columns_in_the_other_order_are_corrected(self):
        """A bank never sells cheaper than it buys, so the pair can be ordered."""
        html = "<tr><td>US Dollar</td><td>47.40</td><td>47.10</td></tr>"
        found = parse_bank_rates(html)
        self.assertAlmostEqual(found["buy"], 47.10)
        self.assertAlmostEqual(found["sell"], 47.40)

    def test_json_feed(self):
        payload = '{"rates":[{"currencyCode":"EUR","buyRate":55.1,"sellRate":55.3},' \
                  '{"currencyCode":"USD","buyRate":47.25,"sellRate":47.35}]}'
        found = parse_bank_rates(payload)
        self.assertAlmostEqual(found["buy"], 47.25)
        self.assertAlmostEqual(found["sell"], 47.35)

    def test_page_furniture_is_not_mistaken_for_a_rate(self):
        html = "<p>Call 19666 for USD services, established 1975.</p>"
        found = parse_bank_rates(html)
        self.assertIsNone(found["buy"])
        self.assertIsNone(found["sell"])

    def test_a_row_with_one_number_yields_a_sell_only(self):
        html = "<tr><td>US Dollar</td><td>47.35</td></tr>"
        found = parse_bank_rates(html)
        self.assertIsNone(found["buy"])
        self.assertAlmostEqual(found["sell"], 47.35)

    def test_rate_rows_beat_a_prose_mention(self):
        html = """<p>Our US Dollar accounts earn 12 percent.</p>
                  <tr><td>US Dollar</td><td>47.25</td><td>47.35</td></tr>"""
        self.assertAlmostEqual(parse_bank_rates(html)["sell"], 47.35)

    def test_empty_input_is_reported_not_guessed(self):
        self.assertEqual(parse_bank_rates("")["sell"], None)
        self.assertEqual(parse_bank_rates(None)["buy"], None)


class CostingRateTests(unittest.TestCase):
    def test_sell_is_what_an_importer_pays(self):
        rate, why = pick_costing_rate(47.25, 47.35)
        self.assertAlmostEqual(rate, 47.35)
        self.assertIn("sell", why)

    def test_buy_only_is_used_but_flagged_as_understating(self):
        rate, why = pick_costing_rate(47.25, None)
        self.assertAlmostEqual(rate, 47.25)
        self.assertIn("understates", why)

    def test_nothing_found_returns_none(self):
        rate, why = pick_costing_rate(None, None)
        self.assertIsNone(rate)
        self.assertIn("no rate", why)

    def test_using_the_mid_instead_of_sell_understates_a_landed_cost(self):
        """The reason to prefer a bank page over an official mid rate."""
        mid, sell = 47.00, 47.35
        cif_usd = 263.27
        gap = cif_usd * (sell - mid)
        self.assertGreater(gap, 90)  # EGP/MT, on a single cargo


if __name__ == "__main__":
    unittest.main()


class JavaScriptPageTests(unittest.TestCase):
    """A converter page renders in the browser, so the rate is rarely in the
    HTML. These cover the two ways to reach it anyway."""

    def test_inline_json_is_found_when_the_markup_has_no_rate_row(self):
        from prometheus_core.fx_sources import embedded_json_blobs
        html = """<html><body><div id="app"></div>
        <script id="__NEXT_DATA__" type="application/json">
        {"props":{"rates":[{"currency":"USD","buy":47.25,"sell":47.35}]}}
        </script></body></html>"""
        self.assertIsNone(parse_bank_rates(html)["sell"])
        blobs = embedded_json_blobs(html)
        self.assertTrue(blobs)
        self.assertAlmostEqual(parse_bank_rates(blobs[0])["sell"], 47.35)

    def test_rate_endpoints_are_discovered_from_the_page(self):
        from prometheus_core.fx_sources import discover_rate_urls
        html = """<script src="/static/main.js"></script>
        <script>var API="/api/v1/exchange-rates";var OTHER="/api/branches";</script>
        <img src="/img/currency-banner.png">"""
        urls = discover_rate_urls(html, "https://www.cibeg.com/en/currency-converter")
        self.assertIn("https://www.cibeg.com/api/v1/exchange-rates", urls)
        self.assertNotIn("https://www.cibeg.com/img/currency-banner.png", urls)

    def test_discovery_stays_on_the_pages_own_host(self):
        from prometheus_core.fx_sources import discover_rate_urls
        html = '<script>var A="https://evil.example.com/api/rates";</script>'
        self.assertEqual(
            discover_rate_urls(html, "https://www.cibeg.com/en/currency-converter"), [])

    def test_script_assets_are_not_mistaken_for_endpoints(self):
        from prometheus_core.fx_sources import discover_rate_urls
        html = '<script src="/assets/currency-converter.js"></script>'
        self.assertEqual(
            discover_rate_urls(html, "https://www.cibeg.com/en/currency-converter"), [])

    def test_converter_shaped_json_with_a_single_rate(self):
        payload = '{"from":"USD","to":"EGP","rate":47.35}'
        self.assertAlmostEqual(parse_bank_rates(payload)["sell"], 47.35)

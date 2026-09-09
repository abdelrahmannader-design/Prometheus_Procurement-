"""CBOT Command Center — the flagship screen of the modern interface.

Two halves, deliberately separated:

``CBOTFeed``            pure Python. Takes the application's state dict and
                        answers questions about CBOT quotes, history, basis
                        and open price risk. No Tk, no I/O, no network — so
                        it is unit-testable head-less and can be reused by
                        exports or an API later.
``CBOTCommandCenter``   the Tk screen composed from the widget kit. It only
                        formats what the feed returns and calls back into
                        the host application for actions.

Every number shown here is derived from data the app already stores
(``market_data``, ``cbot_history``, ``fx_history``, ``local_prices``,
``contracts``). Where an input is missing the screen says so rather than
substituting a zero — the same rule the rest of Prometheus follows for
premiums and replacement cost.
"""

from __future__ import annotations

import datetime as dt
import tkinter as tk

from .charts import AreaChart, BarChart, DonutGauge, RangeMeter, compact_number
from .theme import Theme
from .widgets import (Card, EmptyState, HeroBanner, ListRow, MetricRow,
                      Panel, PillButton, ProgressTrack, SectionTitle,
                      SegmentedControl, StatTile, bind_wraplength)

try:  # single source of truth for the conversion factors
    from prometheus_core.cbot import CBOT_CONV, cbot_conv_factor, commodity_base
except Exception:  # pragma: no cover - kit must import without the core
    CBOT_CONV = {"CORN": 0.3937, "SOYBEAN": 0.36745, "WHEAT": 0.36745, "SBM": 1.1023}

    def commodity_base(commodity):
        return (commodity or "").strip().upper().split("-")[0]

    def cbot_conv_factor(commodity, strict=False):
        return CBOT_CONV.get(commodity_base(commodity),
                             None if strict else 0.3937)

__all__ = ["CBOTFeed", "CBOTCommandCenter", "RANGES", "TRACKED_COMMODITIES"]

#: Range picker options, mapped to a lookback in calendar days.
RANGES = {"30D": 30, "90D": 90, "6M": 182, "1Y": 365, "All": 100000}

#: Commodities that actually price off a CBOT board.
TRACKED_COMMODITIES = ["CORN", "SBM", "SOYBEAN", "WHEAT"]

#: Display unit per board — corn/soybean/wheat trade in cents per bushel,
#: soybean meal in dollars per short ton.
UNITS = {"CORN": "¢/bu", "SOYBEAN": "¢/bu", "WHEAT": "¢/bu", "SBM": "$/st"}


def _f(value, default=None):
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_date(value):
    raw = (str(value) if value is not None else "").strip().split(" ")[0]
    if not raw:
        return None
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y"):
            try:
                return dt.datetime.strptime(raw, fmt).date()
            except ValueError:
                continue
    return None


class CBOTFeed:
    """Read-only view over the application state, focused on CBOT risk."""

    def __init__(self, state, today=None):
        self.state = state or {}
        self._today = today or dt.date.today()

    # -- raw accessors ---------------------------------------------------
    @property
    def market(self) -> dict:
        return self.state.get("market_data", {}) or {}

    def quote(self, commodity="CORN"):
        """Latest stored board quote as ``(price, timestamp)``."""
        quotes = self.market.get("cbot_quotes", {}) or {}
        entry = quotes.get(commodity_base(commodity))
        if isinstance(entry, dict):
            price = _f(entry.get("price"))
            ts = entry.get("fetched_at") or self.market.get("cbot_ts", "")
        else:
            price = _f(entry)
            ts = self.market.get("cbot_ts", "")
        if price is None:
            series = self.history(commodity)
            if series:
                return series[-1][1], series[-1][0]
        return price, ts

    def fx(self):
        fx = self.market.get("fx", {}) or {}
        price = _f(fx.get("price"))
        if price is None:
            series = self.fx_history()
            if series:
                return series[-1][1], series[-1][0]
        return price, fx.get("fetched_at", "")

    def history(self, commodity="CORN", days=None):
        """``[(iso_date, close)]`` for one board, oldest first."""
        base = commodity_base(commodity)
        cutoff = None
        if days:
            cutoff = (self._today - dt.timedelta(days=int(days))).isoformat()
        rows = []
        for entry in self.state.get("cbot_history", []) or []:
            if commodity_base(entry.get("commodity")) != base:
                continue
            date = str(entry.get("date") or "")
            if not date or (cutoff and date < cutoff):
                continue
            price = _f(entry.get("price"), _f(entry.get("close")))
            if price is None:
                continue
            rows.append((date, price))
        rows.sort(key=lambda r: r[0])
        # Collapse duplicate dates, keeping the last write for that day.
        deduped = {}
        for date, price in rows:
            deduped[date] = price
        return sorted(deduped.items())

    def fx_history(self, days=None):
        cutoff = None
        if days:
            cutoff = (self._today - dt.timedelta(days=int(days))).isoformat()
        rows = {}
        for entry in self.state.get("fx_history", []) or []:
            date = str(entry.get("date") or "")
            if not date or (cutoff and date < cutoff):
                continue
            rate = _f(entry.get("rate"), _f(entry.get("price")))
            if rate is not None:
                rows[date] = rate
        return sorted(rows.items())

    # -- derived ---------------------------------------------------------
    def change(self, commodity="CORN", days=30):
        """Percentage move over the window, or ``None`` without two points."""
        series = self.history(commodity, days)
        if len(series) < 2:
            return None
        first, last = series[0][1], series[-1][1]
        if not first:
            return None
        return (last - first) / first * 100.0

    def band(self, commodity="CORN", days=365):
        series = self.history(commodity, days)
        if not series:
            return None, None
        values = [v for _d, v in series]
        return min(values), max(values)

    def spark(self, commodity="CORN", days=90, points=24):
        """A short, evenly-sampled value list for a stat tile sparkline."""
        series = [v for _d, v in self.history(commodity, days)]
        if len(series) <= points:
            return series
        step = len(series) / points
        return [series[min(len(series) - 1, int(i * step))] for i in range(points)]

    def implied_usd_mt(self, commodity="CORN", premium=None):
        """``(CBOT + premium) x factor`` in USD/MT, plus how it was sourced.

        Returns ``(value, note)``. ``value`` is ``None`` when the board quote
        is missing; the premium is never silently assumed to be zero — the
        note says when the figure is a flat, zero-basis reference instead.
        """
        price, _ts = self.quote(commodity)
        factor = cbot_conv_factor(commodity, strict=True)
        if price is None or factor is None:
            return None, "no board quote stored"
        if premium is None:
            premium = self.weighted_premium(commodity)
        if premium is None:
            return price * factor, "flat (no defensible premium — zero basis)"
        return (price + premium) * factor, f"includes {premium:,.1f} premium"

    def replacement_egp_mt(self, commodity="CORN", premium=None):
        """Indicative EGP/MT replacement cost at today's FX, excluding fees."""
        usd, note = self.implied_usd_mt(commodity, premium)
        rate, _ts = self.fx()
        if usd is None or rate is None:
            return None, note if usd is None else "no FX rate stored"
        return usd * rate, note

    def local_all_in(self, commodity="CORN"):
        """Latest logged local price plus its transport, as ``(value, date)``."""
        base = commodity_base(commodity)
        best = None
        for row in self.state.get("local_prices", []) or []:
            if commodity_base(row.get("commodity")) != base:
                continue
            date = str(row.get("date") or "")
            price = _f(row.get("price_egp_mt"))
            if not date or price is None:
                continue
            total = price + (_f(row.get("transport_egp_mt"), 0.0) or 0.0)
            if best is None or date > best[0]:
                best = (date, total)
        return (best[1], best[0]) if best else (None, "")

    def weighted_premium(self, commodity=None):
        """Quantity-weighted premium across open contracts, or ``None``."""
        base = commodity_base(commodity) if commodity else None
        num = den = 0.0
        for contract in (self.state.get("contracts", {}) or {}).values():
            if (contract.get("status") or "Open").strip().lower() != "open":
                continue
            if base and commodity_base(contract.get("commodity")) != base:
                continue
            premium = _f(contract.get("premium_cents"))
            qty = _f(contract.get("qty_mt"), 0.0) or 0.0
            if premium is None or premium <= 0 or qty <= 0:
                continue
            num += premium * qty
            den += qty
        return (num / den) if den else None

    def exposure(self, commodity=None):
        """Open-book price risk: MT, USD, priced split and FX cover."""
        base = commodity_base(commodity) if commodity and commodity != "ALL" else None
        out = {"contracts": 0, "open_mt": 0.0, "open_usd": 0.0,
               "priced_mt": 0.0, "unpriced_mt": 0.0, "fx_unsecured_usd": 0.0,
               "rows": [], "by_commodity": {}}
        for cid, contract in (self.state.get("contracts", {}) or {}).items():
            if (contract.get("status") or "Open").strip().lower() != "open":
                continue
            comm = commodity_base(contract.get("commodity"))
            if base and comm != base:
                continue
            qty = _f(contract.get("qty_mt"), 0.0) or 0.0
            cif = _f(contract.get("cif_usd_mt"))
            usd = qty * cif if cif is not None else 0.0
            priced = bool(contract.get("priced", True)) and cif is not None
            out["contracts"] += 1
            out["open_mt"] += qty
            out["open_usd"] += usd
            if priced:
                out["priced_mt"] += qty
            else:
                out["unpriced_mt"] += qty
            if not _f(contract.get("form4_fx")):
                out["fx_unsecured_usd"] += usd
            bucket = out["by_commodity"].setdefault(
                comm or "—", {"mt": 0.0, "unpriced_mt": 0.0})
            bucket["mt"] += qty
            bucket["unpriced_mt"] += 0.0 if priced else qty
            delivery = _parse_date(contract.get("delivery_date"))
            out["rows"].append({
                "id": cid,
                "label": contract.get("name") or cid,
                "commodity": comm,
                "origin": (contract.get("origin") or "").strip(),
                "supplier": (contract.get("supplier") or "").strip(),
                "qty_mt": qty,
                "priced": priced,
                "premium": _f(contract.get("premium_cents")),
                "delivery": contract.get("delivery_date") or "",
                "days_out": (delivery - self._today).days if delivery else None,
            })
        # Nearest delivery first, unpriced ahead of priced at the same date.
        out["rows"].sort(key=lambda r: (r["priced"],
                                        r["days_out"] if r["days_out"] is not None else 10**6))
        return out

    def coverage_fraction(self, exposure=None):
        exposure = exposure or self.exposure()
        total = exposure["open_mt"]
        if not total:
            return None
        return exposure["priced_mt"] / total

    def signals(self, commodity="CORN", near_days=30):
        """Plain-language findings, most severe first."""
        out = []
        exposure = self.exposure(commodity)
        price, ts = self.quote(commodity)
        unit = UNITS.get(commodity_base(commodity), "")

        if price is None:
            out.append(("rose", "No CBOT quote stored",
                        f"{commodity_base(commodity)} has no board price in market data. "
                        "Refresh quotes before pricing anything off this screen."))
        elif ts and str(ts)[:10] < (self._today - dt.timedelta(days=4)).isoformat():
            out.append(("amber", "Board quote is stale",
                        f"Last {commodity_base(commodity)} quote is from {str(ts)[:10]}."))

        near = [r for r in exposure["rows"]
                if not r["priced"] and r["days_out"] is not None and r["days_out"] <= near_days]
        if near:
            mt = sum(r["qty_mt"] for r in near)
            out.append(("rose", f"{mt:,.0f} MT unpriced inside {near_days} days",
                        ", ".join(f"{r['label']} ({r['days_out']}d)" for r in near[:4])))
        elif exposure["unpriced_mt"] > 0:
            out.append(("amber", f"{exposure['unpriced_mt']:,.0f} MT still unpriced",
                        "CBOT risk is open on these tons until the lots are fixed."))

        if exposure["fx_unsecured_usd"] > 0:
            out.append(("amber", "FX not yet secured",
                        f"USD {exposure['fx_unsecured_usd']:,.0f} of open value has no Form 4 FX."))

        change = self.change(commodity, 30)
        if change is not None and abs(change) >= 5:
            direction = "risen" if change > 0 else "fallen"
            out.append(("sky" if change < 0 else "amber",
                        f"Board has {direction} {abs(change):,.1f}% in 30 days",
                        f"{commodity_base(commodity)} now {price:,.2f} {unit}."
                        if price is not None else ""))

        if self.weighted_premium(commodity) is None:
            out.append(("sky", "No defensible premium on the open book",
                        "Replacement cost is shown flat (zero basis), not as an estimate."))

        if not out:
            out.append(("mint", "Nothing needs attention",
                        "Quotes are current, the open book is priced and FX is covered."))
        return out


class CBOTCommandCenter(tk.Frame):
    """The composed screen. Call :meth:`refresh` whenever state changes."""

    def __init__(self, master, theme: Theme, feed: CBOTFeed, actions=None, **kw):
        self.theme = theme
        self.feed = feed
        self.actions = dict(actions or {})
        super().__init__(master, bg=theme.c("bg"), **kw)
        self._commodity = "CORN"
        self._range = "90D"
        self._overlay_fx = False
        self.columnconfigure(0, weight=1)
        # Sections keep their requested height rather than competing for the
        # window: the screen lives in a scrolling tab, and a row that shrinks
        # below its request silently clips text instead of scrolling.
        self._build()

    # -- helpers ---------------------------------------------------------
    def _act(self, name):
        callback = self.actions.get(name)
        return callback if callable(callback) else (lambda: None)

    @property
    def unit(self):
        return UNITS.get(self._commodity, "")

    # -- construction ----------------------------------------------------
    def _build(self):
        t = self.theme
        self.hero = HeroBanner(self, t, height=196)
        self.hero.grid(row=0, column=0, sticky="ew", pady=(6, 10))
        self.hero.set_actions([
            ("Refresh quotes", self._act("refresh_quotes")),
            ("Basis Tracker", self._act("open_basis")),
            ("CBOT Slots", self._act("open_slots")),
        ])
        # The desk covers four boards, not one: swipe the hero (drag, the
        # chevrons, the dots, Shift+wheel or Left/Right) to change board.
        self.hero.set_nav(TRACKED_COMMODITIES,
                          TRACKED_COMMODITIES.index(self._commodity),
                          self._on_board_swipe)

        self._build_board_strip()
        self._build_tiles()
        self._build_main()
        self._build_lower()

    def _build_board_strip(self):
        """One mini-card per board — the answer to "it only shows CORN".

        The hero shows the selected board in full; this strip keeps the
        other three in view with their price and 30-day move, and selects
        one on click.
        """
        t = self.theme
        strip = tk.Frame(self, bg=t.c("bg"))
        strip.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        self.board_cards = {}
        for col, comm in enumerate(TRACKED_COMMODITIES):
            strip.columnconfigure(col, weight=1, uniform="boards")
            card = Panel(strip, t, radius="lg", cursor="hand2")
            card.grid(row=0, column=col, sticky="nsew",
                      padx=(0 if col == 0 else 6, 0))
            card.columnconfigure(1, weight=1)
            fill = card.fill

            accent = tk.Frame(card, bg=t.c("stroke"), width=4)
            accent.grid(row=0, column=0, rowspan=2, sticky="ns",
                        padx=(12, 0), pady=12)
            name = tk.Label(card, text=comm, bg=fill, fg=t.c("ink"), anchor="w",
                            font=t.font("caption", "bold"))
            name.grid(row=0, column=1, sticky="w", padx=(10, 12), pady=(12, 0))
            price_var = tk.StringVar(value="—")
            price = tk.Label(card, textvariable=price_var, bg=fill,
                             fg=t.c("ink"), anchor="w",
                             font=t.font("body_lg", "bold"))
            price.grid(row=1, column=1, sticky="w", padx=(10, 12), pady=(0, 12))
            delta_var = tk.StringVar(value="")
            delta = tk.Label(card, textvariable=delta_var, bg=fill,
                             fg=t.c("ink_3"), anchor="e",
                             font=t.font("caption", "bold"))
            delta.grid(row=1, column=2, sticky="e", padx=(0, 14), pady=(0, 12))

            self.board_cards[comm] = {
                "card": card, "accent": accent, "name": name,
                "price": price, "price_var": price_var,
                "delta": delta, "delta_var": delta_var, "fill": fill,
            }
            for widget in (card, accent, name, price, delta):
                widget.bind("<Button-1>",
                            lambda _e, c=comm: self._select_board(c))

    def _select_board(self, commodity):
        """Point every panel on the screen at one board."""
        if commodity not in TRACKED_COMMODITIES:
            return
        self._commodity = commodity
        index = TRACKED_COMMODITIES.index(commodity)
        try:
            self.hero.set_nav_index(index)
            self.commodity_pick.set_value(commodity)
        except Exception:
            pass
        self.refresh()

    def _on_board_swipe(self, index):
        self._select_board(TRACKED_COMMODITIES[index])

    def _refresh_board_strip(self):
        t = self.theme
        for comm, parts in getattr(self, "board_cards", {}).items():
            price, _ts = self.feed.quote(comm)
            change = self.feed.change(comm, 30)
            unit = UNITS.get(comm, "")
            parts["price_var"].set(
                f"{price:,.2f} {unit}".strip() if price is not None else "—")
            if change is None:
                parts["delta_var"].set("")
                tone_ink = t.c("ink_3")
            else:
                parts["delta_var"].set(f"{change:+.1f}%")
                # A falling board is good news for a buyer.
                tone_ink = t.c("mint") if change < 0 else t.c("rose")
            parts["delta"].configure(fg=tone_ink)
            active = comm == self._commodity
            parts["accent"].configure(
                bg=t.c("brand") if active else t.c("stroke"))
            parts["name"].configure(
                fg=t.c("brand_ink") if active else t.c("ink_2"),
                font=t.font("caption", "bold"))
            parts["price"].configure(fg=t.c("ink") if active else t.c("ink_2"))

    def _build_tiles(self):
        t = self.theme
        strip = tk.Frame(self, bg=t.c("bg"))
        strip.grid(row=2, column=0, sticky="ew")
        self.tiles = {}
        specs = [
            ("board",       "Board price",      "◈", "brand"),
            ("replacement", "Replacement cost", "⇄", "violet"),
            ("unpriced",    "Unpriced tons",    "◔", "amber"),
            ("fx",          "USD / EGP",        "$", "sky"),
        ]
        for col, (key, caption, glyph, tone) in enumerate(specs):
            strip.columnconfigure(col, weight=1, uniform="tiles")
            tile = StatTile(strip, t, caption=caption, glyph=glyph, tone=tone,
                            hint="—")
            tile.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 6, 0))
            self.tiles[key] = tile

    def _build_main(self):
        t = self.theme
        main = tk.Frame(self, bg=t.c("bg"))
        main.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
        main.columnconfigure(0, weight=3, uniform="main")
        main.columnconfigure(1, weight=2, uniform="main")
        main.rowconfigure(0, weight=1)

        # -- price history ------------------------------------------------
        chart_card = Card(main, t, radius="xl")
        chart_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        body = chart_card.body
        body.columnconfigure(0, weight=1)
        body.rowconfigure(2, weight=1)

        head = SectionTitle(body, t, "Board history",
                            "Daily settlement stored by Prometheus",
                            ground=chart_card.fill)
        head.grid(row=0, column=0, sticky="ew")
        self._chart_title = head.title_var
        self._chart_sub = head.subtitle_var

        controls = tk.Frame(body, bg=chart_card.fill)
        controls.grid(row=1, column=0, sticky="ew", pady=(12, 8))
        controls.columnconfigure(1, weight=1)
        self.commodity_pick = SegmentedControl(
            controls, t, TRACKED_COMMODITIES, command=self._on_commodity,
            value=self._commodity, ground=chart_card.fill)
        self.commodity_pick.grid(row=0, column=0, sticky="w")
        self.range_pick = SegmentedControl(
            controls, t, list(RANGES.keys()), command=self._on_range,
            value=self._range, ground=chart_card.fill)
        self.range_pick.grid(row=0, column=2, sticky="e")

        self.chart = AreaChart(body, t, ground=chart_card.fill, height=250,
                               value_format=lambda v: f"{v:,.2f} {self.unit}",
                               on_hover=self._on_chart_hover)
        self.chart.grid(row=2, column=0, sticky="nsew")

        self.readout = tk.Label(body, text="", bg=chart_card.fill,
                                fg=t.c("ink_3"), font=t.font("caption"),
                                anchor="w")
        self.readout.grid(row=3, column=0, sticky="ew", pady=(6, 0))

        # -- right column -------------------------------------------------
        right = tk.Frame(main, bg=t.c("bg"))
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        cover = Card(right, t, radius="xl")
        cover.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        cb = cover.body
        cb.columnconfigure(1, weight=1)
        SectionTitle(cb, t, "Price cover", "Open book fixed vs still exposed",
                     ground=cover.fill).grid(row=0, column=0, columnspan=2,
                                             sticky="ew", pady=(0, 10))
        self.cover_gauge = DonutGauge(cb, t, ground=cover.fill, size=132,
                                      thickness=15)
        self.cover_gauge.grid(row=1, column=0, rowspan=4, sticky="w")
        self.cover_rows = {}
        for idx, (key, label, tone) in enumerate((
                ("priced", "Priced", "mint"),
                ("unpriced", "Unpriced", "amber"),
                ("fx", "FX unsecured", "rose"))):
            row = MetricRow(cb, t, label=label, value="—", tone=tone,
                            ground=cover.fill)
            row.grid(row=1 + idx, column=1, sticky="ew", padx=(14, 0), pady=3)
            self.cover_rows[key] = row
        self.cover_track = ProgressTrack(cb, t, ground=cover.fill, height=9)
        self.cover_track.grid(row=4, column=1, sticky="ew", padx=(14, 0), pady=(8, 0))

        band = Card(right, t, radius="xl")
        band.grid(row=1, column=0, sticky="nsew")
        bb = band.body
        bb.columnconfigure(0, weight=1)
        SectionTitle(bb, t, "Where today sits", "Against the stored 12-month band",
                     ground=band.fill).grid(row=0, column=0, sticky="ew")
        self.range_meter = RangeMeter(bb, t, ground=band.fill, height=72,
                                      value_format=lambda v: f"{v:,.1f}")
        self.range_meter.grid(row=1, column=0, sticky="ew", pady=(10, 4))
        self.basis_rows = {}
        for idx, (key, label) in enumerate((
                ("implied", "CBOT-implied goods"),
                ("local", "Local all-in"),
                ("edge", "Gap before freight"))):
            row = MetricRow(bb, t, label=label, value="—", ground=band.fill)
            row.grid(row=2 + idx, column=0, sticky="ew", pady=2)
            self.basis_rows[key] = row
        self.basis_note = tk.Label(bb, text="", bg=band.fill, fg=t.c("ink_3"),
                                   font=t.font("micro"), anchor="w",
                                   justify="left")
        self.basis_note.grid(row=5, column=0, sticky="ew", pady=(8, 0))
        bind_wraplength(self.basis_note, bb, pad=2)

    def _build_lower(self):
        t = self.theme
        lower = tk.Frame(self, bg=t.c("bg"))
        lower.grid(row=4, column=0, sticky="nsew", pady=(12, 8))
        lower.columnconfigure(0, weight=3, uniform="lower")
        lower.columnconfigure(1, weight=2, uniform="lower")
        lower.rowconfigure(0, weight=1)

        book = Card(lower, t, radius="xl")
        book.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        bb = book.body
        bb.columnconfigure(0, weight=1)
        bb.rowconfigure(1, weight=1)
        head = SectionTitle(bb, t, "Open price risk",
                            "Nearest delivery first — unpriced tons lead",
                            ground=book.fill)
        head.grid(row=0, column=0, sticky="ew")
        PillButton(head.actions, t, "Open contracts", variant="soft",
                   size="caption", command=self._act("open_contracts"),
                   ground=book.fill).pack(side="right")
        self.book_host = tk.Frame(bb, bg=book.fill)
        self.book_host.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        self.book_host.columnconfigure(0, weight=1)
        self._book_fill = book.fill

        self.mix_caption = tk.Label(
            bb, text="Open MT by commodity — the board in focus is highlighted",
            bg=book.fill, fg=self.theme.c("ink_3"),
            font=self.theme.font("micro"), anchor="w")
        self.mix_caption.grid(row=2, column=0, sticky="ew", pady=(12, 2))
        self.mix_chart = BarChart(bb, t, ground=book.fill, height=118,
                                  tone="brand",
                                  value_format=lambda v: f"{v:,.0f} MT")
        self.mix_chart.grid(row=3, column=0, sticky="ew")

        signals = Card(lower, t, radius="xl")
        signals.grid(row=0, column=1, sticky="nsew")
        sb = signals.body
        sb.columnconfigure(0, weight=1)
        sb.rowconfigure(1, weight=1)
        SectionTitle(sb, t, "Signals", "What this screen wants you to know",
                     ground=signals.fill).grid(row=0, column=0, sticky="ew")
        self.signal_host = tk.Frame(sb, bg=signals.fill)
        self.signal_host.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        self.signal_host.columnconfigure(0, weight=1)
        self._signal_fill = signals.fill

    # -- interaction -----------------------------------------------------
    def _on_commodity(self, value):
        self._select_board(value)

    def _on_range(self, value):
        self._range = value
        self.refresh()

    def _on_chart_hover(self, point):
        if not point:
            self.readout.configure(text="")
            return
        label, value = point
        self.readout.configure(
            text=f"{label}   ·   {value:,.2f} {self.unit}")

    # -- data ------------------------------------------------------------
    def refresh(self):
        """Repaint every panel from the feed. Safe to call repeatedly."""
        feed = self.feed
        comm = self._commodity
        unit = self.unit
        price, ts = feed.quote(comm)
        change_30 = feed.change(comm, 30)
        exposure = feed.exposure(comm)

        # -- hero ---------------------------------------------------------
        hour = dt.datetime.now().hour
        greeting = "Good morning" if hour < 12 else ("Good afternoon" if hour < 18 else "Good evening")
        delta_text = f"{change_30:+.1f}% · 30d" if change_30 is not None else "no 30-day history"
        self.hero.set_content(
            eyebrow=f"{greeting} · CBOT desk",
            headline="CBOT Command Center",
            support=("Live board, basis and the tons still exposed to it. "
                     "Swipe or use ‹ › to change board."),
            metric_label=f"{comm} {unit}".strip(),
            metric_value=f"{price:,.2f}" if price is not None else "—",
            metric_delta=delta_text,
            metric_delta_tone=("mint" if (change_30 or 0) < 0 else "rose")
            if change_30 is not None else "sky",
            footnote=f"quote stored {str(ts)[:10]}" if ts else "no quote timestamp",
        )

        self._refresh_board_strip()
        self._refresh_tiles(comm, price, change_30, exposure)
        self._refresh_chart(comm, unit)
        self._refresh_cover(exposure)
        self._refresh_band(comm, unit)
        self._refresh_book(exposure)
        self._refresh_signals(comm)

    def _refresh_tiles(self, comm, price, change_30, exposure):
        feed, unit = self.feed, self.unit
        change_7 = feed.change(comm, 7)
        self.tiles["board"].set(
            caption=f"{comm} board  {unit}",
            value=f"{price:,.2f}" if price is not None else "—",
            hint="7-day move" if change_7 is not None else "no recent history",
            delta=f"{change_7:+.1f}%" if change_7 is not None else "",
            delta_tone="mint" if (change_7 or 0) < 0 else "rose",
            spark=feed.spark(comm, 90))

        replacement, note = feed.replacement_egp_mt(comm)
        self.tiles["replacement"].set(
            caption="Replacement EGP/MT",
            value=f"{replacement:,.0f}" if replacement is not None else "—",
            hint=note,
            delta="", spark=[])

        unpriced = exposure["unpriced_mt"]
        share = (unpriced / exposure["open_mt"] * 100.0) if exposure["open_mt"] else None
        self.tiles["unpriced"].set(
            caption="Unpriced tons",
            value=f"{unpriced:,.0f} MT",
            hint=f"of {exposure['open_mt']:,.0f} MT open on {comm}",
            delta=f"{share:,.0f}%" if share is not None else "",
            delta_tone="rose" if (share or 0) > 40 else "amber" if share else "sky",
            spark=[])

        rate, fx_ts = feed.fx()
        fx_series = [v for _d, v in feed.fx_history(90)]
        fx_change = None
        if len(fx_series) >= 2 and fx_series[0]:
            fx_change = (fx_series[-1] - fx_series[0]) / fx_series[0] * 100.0
        self.tiles["fx"].set(
            caption="USD / EGP",
            value=f"{rate:,.4f}" if rate is not None else "—",
            hint=f"stored {str(fx_ts)[:10]}" if fx_ts else "no FX stored",
            delta=f"{fx_change:+.1f}% · 90d" if fx_change is not None else "",
            delta_tone="rose" if (fx_change or 0) > 0 else "mint",
            spark=fx_series[-24:])

    def _refresh_chart(self, comm, unit):
        days = RANGES.get(self._range, 90)
        series = self.feed.history(comm, days)
        # Trim the x labels to DD-MM so a year of dates still reads.
        points = [(d[5:], v) for d, v in series]
        self.chart.set_series(points)
        self._chart_title.set(f"{comm} board history")
        self._chart_sub.set(
            f"{len(series)} stored closes · {self._range} · {unit}"
            if series else "No stored closes for this board yet")
        self.readout.configure(text="")

    def _refresh_cover(self, exposure):
        open_mt = exposure["open_mt"]
        priced = exposure["priced_mt"]
        unpriced = exposure["unpriced_mt"]
        if open_mt:
            pct = priced / open_mt
            self.cover_gauge.set([(pct, "mint"), (unpriced / open_mt, "amber")],
                                 f"{pct * 100:,.0f}%", "priced")
            self.cover_track.set_segments([(pct, "mint"),
                                           (unpriced / open_mt, "amber")])
        else:
            self.cover_gauge.set([], "—", "no open book")
            self.cover_track.set_segments([])
        self.cover_rows["priced"].set(f"{priced:,.0f} MT")
        self.cover_rows["unpriced"].set(f"{unpriced:,.0f} MT")
        self.cover_rows["fx"].set(f"USD {compact_number(exposure['fx_unsecured_usd'], 1)}")

    def _refresh_band(self, comm, unit):
        low, high = self.feed.band(comm, 365)
        price, _ts = self.feed.quote(comm)
        if None not in (low, high) and price is not None and high > low:
            self.range_meter.set(low, high, price, labels=("12m low", "12m high"))
        else:
            self.range_meter.set(None, None, None)

        implied, note = self.feed.replacement_egp_mt(comm)
        local, local_date = self.feed.local_all_in(comm)
        self.basis_rows["implied"].set(
            f"{implied:,.0f} EGP/MT" if implied is not None else "—")
        self.basis_rows["local"].set(
            f"{local:,.0f} EGP/MT" if local is not None else "—")
        if implied is not None and local is not None:
            self.basis_rows["edge"].set(f"{local - implied:+,.0f} EGP/MT")
        else:
            self.basis_rows["edge"].set("—")
        parts = [f"CBOT-implied goods value {note}."]
        if local_date:
            parts.append(f"Local price logged {local_date}.")
        parts.append("The gap is goods-only: freight, clearing, VAT and finance "
                     "are not in it. Use Analysis → Inventory vs Market for the "
                     "landed comparison.")
        self.basis_note.configure(text=" ".join(parts))

    def _refresh_book(self, exposure):
        for child in self.book_host.winfo_children():
            child.destroy()
        rows = exposure["rows"][:6]
        if not rows:
            EmptyState(self.book_host, self.theme, glyph="◎",
                       title="No open contracts",
                       body="Nothing on this board is exposed to CBOT right now.",
                       ground=self._book_fill).grid(row=0, column=0, sticky="ew")
        else:
            for idx, row in enumerate(rows):
                unpriced = not row["priced"]
                days = row["days_out"]
                when = (f"{days}d to delivery" if days is not None and days >= 0
                        else (f"{abs(days)}d overdue" if days is not None else "no delivery date"))
                subtitle = " · ".join(x for x in (
                    row["commodity"], row["origin"], row["supplier"], when) if x)
                listing = ListRow(
                    self.book_host, self.theme, ground=self._book_fill,
                    glyph="◔" if unpriced else "✓",
                    tone="amber" if unpriced else "mint",
                    on_click=(lambda cid=row["id"]: self._act("open_contract")(cid))
                    if self.actions.get("open_contract") else None)
                listing.grid(row=idx, column=0, sticky="ew", pady=1)
                listing.set(title=row["label"], subtitle=subtitle,
                            value=f"{row['qty_mt']:,.0f} MT",
                            chip="Unpriced" if unpriced else "Priced",
                            chip_tone="amber" if unpriced else "mint")

        # The mix is always the whole open book: knowing CORN is 60% of the
        # exposure is the point, and that is invisible in a filtered view.
        by_comm = self.feed.exposure()["by_commodity"]
        bars = [(name, data["mt"],
                 "brand" if name == self._commodity else "sky")
                for name, data in
                sorted(by_comm.items(), key=lambda kv: -kv[1]["mt"])][:6]
        self.mix_chart.set_bars(bars)

    def _refresh_signals(self, comm):
        for child in self.signal_host.winfo_children():
            child.destroy()
        for idx, (tone, title, detail) in enumerate(self.feed.signals(comm)):
            card = Card(self.signal_host, self.theme, radius="md",
                        fill="surface_2", pad=12, shadow=False, border=True,
                        ground=self._signal_fill, accent=self.theme.tone(tone)[0])
            card.grid(row=idx, column=0, sticky="ew", pady=3)
            card.body.columnconfigure(0, weight=1)
            title_lbl = tk.Label(card.body, text=title, bg=card.fill,
                                 fg=self.theme.c("ink"),
                                 font=self.theme.font("caption", "bold"),
                                 anchor="w", justify="left")
            title_lbl.grid(row=0, column=0, sticky="ew")
            bind_wraplength(title_lbl, self.signal_host, pad=28)
            if detail:
                detail_lbl = tk.Label(card.body, text=detail, bg=card.fill,
                                      fg=self.theme.c("ink_3"),
                                      font=self.theme.font("micro"),
                                      anchor="w", justify="left")
                detail_lbl.grid(row=1, column=0, sticky="ew", pady=(3, 0))
                bind_wraplength(detail_lbl, self.signal_host, pad=28)

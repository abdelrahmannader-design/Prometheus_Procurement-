"""Did the contract save money, judged tonne by tonne as it was eaten.

The savings already in the app answer narrower questions. The Savings
Tracker values a closed cargo at one date, which ignores that it is
consumed over months while the market moves underneath it. Inventory vs
Market values what is still in the yard at today's prices, and says
nothing about the tonnes already burned.

This values every tonne on the day it was actually consumed, against two
alternatives available that day:

    vs local   consumed_mt x (local price that day        - what it cost)
    vs CBOT    consumed_mt x (board + basis, converted
                              + the same port, clearance
                              and inland freight          - what it cost)

The import alternative carries the same landed fees as the cargo it is set
against, so the comparison is like for like and what is left is the
market: the board that day against the contract's own fixing, that day's
basis against the premium paid, and that day's FX against the cost FX.

Weighting by the tonnes genuinely burned on each day is the point. A
cargo landed in July and eaten through October met a different market
every week, and a single valuation date either flatters or buries that
depending on where the date happens to fall.

Prices are looked up on-or-before each date, because boards do not trade
at weekends and a local price is not logged every day. A draw whose
reference price is older than a set tolerance is reported as stale rather
than silently valued against a number from weeks earlier.

Pure functions only — no Tk, no I/O.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Callable

from .numbers import to_float

__all__ = ["CONSUMPTION_SAVINGS_VERSION", "DEFAULT_STALE_DAYS",
           "consumption_draws", "value_draws", "savings_report",
           "nearest_on_or_before", "series_from_rows"]

CONSUMPTION_SAVINGS_VERSION = "1.3"

#: A reference price older than this is still used — refusing to value a
#: tonne helps nobody — but the row is marked so a total built largely on
#: stale references cannot pass for a precise one.
DEFAULT_STALE_DAYS = 7


def _date(value):
    text = str(value or "")[:10]
    if not text:
        return None
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        return None


def _base(commodity):
    return (commodity or "").strip().upper().split("-")[0]


def _origin(row):
    """Origin of a lot: the explicit field, else the commodity suffix.

    A consumption entry says CORN, never CORN-BRZ — the yard records what
    was burned, not whose cargo it came out of. FIFO answers that, so the
    origin belongs to the layer the tonne was drawn from, which is why it
    is resolved here and not from the event.
    """
    explicit = (row.get("origin") or "").strip().upper()
    if explicit:
        return explicit
    parts = (row.get("commodity") or "").strip().upper().split("-", 1)
    return parts[1] if len(parts) == 2 else ""


def series_from_rows(rows, date_key="date", value_key="price_egp_mt",
                     commodity=None, extra=None, extra_default=None):
    """A ``{date: value}`` map from logged rows, newest wins per date.

    ``extra`` names a second field added to the first, which is how a local
    price plus its transport becomes one all-in figure without the caller
    having to pre-flatten the rows.

    ``extra_default`` is used when a row has no ``extra`` of its own, the
    way a local purchase without a transport figure is costed at the app's
    default rate — so a local price and a local purchase are built alike.

    ``value_key`` may be a tuple of field names tried in order. The app's
    CBOT history stores its close as ``price``, while older rows and imports
    use ``close``; reading only one of them silently loses the whole board.
    """
    out = {}
    want = _base(commodity) if commodity else None
    keys = (value_key,) if isinstance(value_key, str) else tuple(value_key)
    for row in rows or []:
        if want and _base(row.get("commodity")) != want:
            continue
        date = _date(row.get(date_key))
        value = next((v for v in (to_float(row.get(k), None) for k in keys)
                      if v is not None), None)
        if date is None or value is None:
            continue
        if extra:
            add = to_float(row.get(extra), None)
            if add is None:
                add = to_float(extra_default, 0.0) or 0.0
            value += add
        out[date] = value
    return out


def nearest_on_or_before(series, date):
    """The most recent value at or before ``date``, with its own date.

    Returns ``(value, date, age_days)`` or ``(None, None, None)``. Looking
    forward would value a tonne against a price that did not exist when it
    was consumed, so the search is strictly backwards.
    """
    if not series or date is None:
        return None, None, None
    best = None
    for when, value in series.items():
        if when <= date and (best is None or when > best):
            best = when
    if best is None:
        return None, None, None
    return series[best], best, (date - best).days


def within(draws, start=None, end=None):
    """The draws that fall inside a date window, ends included."""
    first, last = _date(start), _date(end)
    if not (first or last):
        return list(draws or [])
    return [d for d in draws or []
            if (not first or d["date"] >= first)
            and (not last or d["date"] <= last)]


def stock_layers(lots, commodity=None):
    """The cargoes of a commodity, oldest first — the FIFO queue itself.

    Shared with the coverage report so that what a reader is told about a
    cargo comes from the same queue the draws were taken out of, rather
    than from a second pass that could disagree with it.
    """
    want = _base(commodity) if commodity else None
    layers = []
    for lot in lots or []:
        if not isinstance(lot, dict):
            continue
        base = _base(lot.get("base_commodity") or lot.get("commodity"))
        if want and base != want:
            continue
        landed = _date(lot.get("delivery_date") or lot.get("storage_start"))
        qty = to_float(lot.get("original_mt") or lot.get("qty_mt"), 0.0) or 0.0
        if landed is None or qty <= 0:
            continue
        layers.append({
            "date": landed, "left": qty, "qty": qty, "base": base,
            "cost": to_float(lot.get("cost_egp_mt"), None),
            "lot_id": lot.get("lot_id") or lot.get("contract_id") or "",
            "ref": (lot.get("contract_ref") or lot.get("name")
                    or lot.get("contract_id") or "").strip(),
            "origin": _origin(lot),
            "supplier": (lot.get("supplier") or "").strip(),
        })
    layers.sort(key=lambda x: (x["date"], str(x["lot_id"])))
    return layers


def cargo_coverage(lots, all_draws, commodity=None, start=None, end=None,
                   origin=None):
    """Every cargo in scope and how much of it the consumption has reached.

    Without this the tab looks like it has lost contracts: a cargo nobody
    has eaten into yet has no realised saving, so it cannot appear as a
    draw, and the only honest answer to "where are the rest?" is to name
    them and say why they are not there.
    """
    want_origin = (origin or "").strip().upper() or None
    first, last = _date(start), _date(end)
    drawn_all, drawn_window, drawn_after = {}, {}, {}
    drawn_estimated, drawn_count, count_dates = {}, {}, {}
    for draw in all_draws or []:
        key = draw.get("lot_id") or draw.get("contract_ref") or ""
        drawn_all[key] = drawn_all.get(key, 0.0) + draw["mt"]
        if draw.get("kind") == "count":
            # Cleared by a physical count: consumed, but on no known day, so
            # it belongs to no window and is reported on its own.
            drawn_count[key] = drawn_count.get(key, 0.0) + draw["mt"]
            count_dates[key] = draw["date"]
            continue
        if last and draw["date"] > last:
            bucket = drawn_after
        elif first and draw["date"] < first:
            continue
        else:
            bucket = drawn_window
            if draw.get("kind") == "estimated":
                drawn_estimated[key] = drawn_estimated.get(key, 0.0) + draw["mt"]
        bucket[key] = bucket.get(key, 0.0) + draw["mt"]

    out = []
    for layer in stock_layers(lots, commodity):
        if want_origin and (layer["origin"] or "") != want_origin:
            continue
        key = layer["lot_id"] or layer["ref"]
        total = drawn_all.get(key, 0.0)
        here = drawn_window.get(key, 0.0)
        # Order matters: a cargo consumed outside the window is either still
        # ahead of it or already behind it, and calling both "earlier" would
        # tell a reader the opposite of what happened.
        if here > 1e-9:
            state, why = "drawn", "consumed in this period"
        elif last and layer["date"] > last:
            state, why = "later", "landed after this period"
        elif drawn_after.get(key, 0.0) > 1e-9:
            state, why = "later", "consumed after this period"
        elif total - drawn_count.get(key, 0.0) > 1e-9:
            state, why = "earlier", "consumed before this period"
        elif drawn_count.get(key, 0.0) > 1e-9:
            state = "counted"
            why = (f"consumed before the stock count of "
                   f"{count_dates[key].isoformat()} (day not recorded)")
        else:
            state, why = "untouched", "still in stock, FIFO has not reached it"
        out.append({
            "lot_id": layer["lot_id"], "key": layer["ref"] or layer["lot_id"],
            "origin": layer["origin"] or "(no origin)",
            "supplier": layer["supplier"],
            "landed": layer["date"].isoformat(),
            "qty_mt": layer["qty"], "cost_egp_mt": layer["cost"],
            "drawn_mt": here, "drawn_total_mt": total,
            "drawn_estimated_mt": drawn_estimated.get(key, 0.0),
            "drawn_count_mt": drawn_count.get(key, 0.0),
            "count_date": (count_dates[key].isoformat()
                           if key in count_dates else ""),
            "remaining_mt": max(layer["qty"] - total, 0.0),
            "state": state, "why": why,
        })
    return out


KIND_LABELS = {"actual": "logged", "estimated": "estimated", "count": "stock count"}


def draws_from_inventory(raw_draws, commodity=None, origin=None):
    """Savings draws from the withdrawals the inventory FIFO already made.

    The inventory view decides what has been consumed — logged entries, the
    daily-rate estimate after the last one, and physical stock counts — so
    the savings report reads the same withdrawals rather than walking the
    log a second time and reaching a different answer about what is left.
    Every draw keeps its ``kind`` so a reader can tell recorded tonnes from
    modelled ones.
    """
    want = _base(commodity) if commodity else None
    want_origin = (origin or "").strip().upper() or None
    out = []
    for raw in raw_draws or []:
        when = _date(raw.get("date"))
        mt = to_float(raw.get("mt"), 0.0) or 0.0
        if when is None or mt <= 1e-9:
            continue
        sourced = (raw.get("contract_ref") or "") != "(unsourced)"
        base = _base(raw.get("commodity")) or want or ""
        out.append({
            "date": when, "commodity": want or base, "mt": mt,
            "cost_egp_mt": to_float(raw.get("cost_egp_mt"), None),
            "lot_id": raw.get("lot_id") or raw.get("contract_id") or "",
            "contract_ref": ((raw.get("contract_ref") or raw.get("contract_id")
                              or "").strip() or "(no reference)"),
            "origin": (_origin(raw) or "(no origin)") if sourced else "(unsourced)",
            "supplier": (raw.get("supplier") or "").strip(),
            "landed": (_date(raw.get("delivery_date")).isoformat()
                       if sourced and _date(raw.get("delivery_date")) else ""),
            "kind": raw.get("kind") or "actual",
        })
    out.sort(key=lambda d: d["date"])
    if want_origin:
        # After the walk, for the reason given in consumption_draws.
        out = [d for d in out if d["origin"] == want_origin]
    return out


def consumption_draws(lots, events, commodity=None, start=None, end=None,
                     origin=None):
    """Walk consumption FIFO and record every draw against its layer.

    The app's inventory walk returns the layers that survive; this returns
    the withdrawals, because a withdrawal is what carries a date, a tonnage
    and the cost of the specific layer it came out of — the three things a
    saving needs.
    """
    want = _base(commodity) if commodity else None
    want_origin = (origin or "").strip().upper() or None

    layers = stock_layers(lots, commodity)

    uses = []
    for event in events or []:
        if not isinstance(event, dict) or event.get("is_adjustment"):
            continue
        base = _base(event.get("commodity"))
        if want and base != want:
            continue
        when = _date(event.get("date"))
        qty = to_float(event.get("consumed_mt") or event.get("qty_mt"), 0.0) or 0.0
        if when is None or qty <= 0:
            continue
        uses.append({"date": when, "mt": qty, "base": base})
    uses.sort(key=lambda x: x["date"])

    draws = []
    for use in uses:
        outstanding = use["mt"]
        for layer in layers:
            if outstanding <= 1e-9:
                break
            if layer["base"] != use["base"] or layer["left"] <= 1e-9:
                continue
            # A layer cannot supply a tonne before it landed.
            if layer["date"] > use["date"]:
                continue
            take = min(layer["left"], outstanding)
            layer["left"] -= take
            outstanding -= take
            draws.append({
                "date": use["date"], "commodity": use["base"], "mt": take,
                "cost_egp_mt": layer["cost"], "lot_id": layer["lot_id"],
                "contract_ref": layer["ref"],
                "origin": layer["origin"] or "(no origin)",
                "supplier": layer["supplier"],
                "landed": layer["date"].isoformat(),
            })
        if outstanding > 1e-9:
            # Consumed more than any layer can account for. Reported rather
            # than dropped: a gap in the receipts is worth seeing.
            draws.append({
                "date": use["date"], "commodity": use["base"], "mt": outstanding,
                "cost_egp_mt": None, "lot_id": "", "contract_ref": "(unsourced)",
                "origin": "(unsourced)", "supplier": "", "landed": "",
            })

    if want_origin:
        # Filtered after the walk, not before: dropping a cargo from the
        # queue first would hand its tonnes to the wrong layer and change
        # what every later draw cost.
        draws = [d for d in draws if d.get("origin") == want_origin]
    return within(draws, start, end)


def value_draws(draws, local_series=None, cbot_series=None, fx_series=None,
                basis_for: Callable[[dt.date], Any] | None = None,
                factor=0.3937, stale_days=DEFAULT_STALE_DAYS,
                local_lookup: Callable[[dict], Any] | None = None,
                import_fees_for: Callable[[dict], Any] | None = None,
                import_terms_for: Callable[[dict], Any] | None = None):
    """Price each draw against what that day's alternatives would have cost.

    ``import_fees_for(draw)`` gives the discharge + clearance + inland
    freight an import landed that day would carry, in EGP/MT; ``None`` from
    it leaves the import alternative unpriced rather than guessed. Without
    it no fees are added (the earlier, CIF-only behaviour).

    ``import_terms_for(draw)`` gives the cargo's ``(cif_usd_mt, cost_fx,
    premium)``. For a CBOT + premium cargo the saving against importing is
    then split, per MT, into the board move (board that day − the
    contract's implied fixing), basis (that day's basis − the premium paid)
    and FX (that day's FX − the cost FX, on the CIF); whatever those do not
    explain — flat-price cargoes, local purchases — is left unsplit.

    A positive saving means the tonne cost less than the alternative, which
    is the direction a reader expects from the word.

    ``local_lookup(draw)`` returns ``(price, date, age_days, key)`` for that
    draw, so the local alternative can follow the cargo's own origin —
    Brazilian corn against the Brazilian local price — instead of one
    series for every origin. Without it ``local_series`` is used for all.
    """
    rows = []
    for draw in draws or []:
        when = draw["date"]
        cost = to_float(draw.get("cost_egp_mt"), None)
        if local_lookup:
            found = local_lookup(draw) or (None, None, None, "")
            local, local_date, local_age = found[:3]
            local_key = found[3] if len(found) > 3 else ""
        else:
            local, local_date, local_age = nearest_on_or_before(local_series, when)
            local_key = ""
        # The same local price on the day the cargo landed. Set against the
        # cost it gives the saving the purchase made on arrival — what the
        # Savings Tracker measures — and set against the price on the day of
        # use it gives how far the market moved while the corn sat in stock.
        landed = _date(draw.get("landed"))
        local_del = None
        if landed is not None:
            if local_lookup:
                local_del = (local_lookup({**draw, "date": landed})
                             or (None,))[0]
            else:
                local_del = nearest_on_or_before(local_series, landed)[0]
        board, board_date, board_age = nearest_on_or_before(cbot_series, when)
        rate, fx_date, fx_age = nearest_on_or_before(fx_series, when)
        basis = to_float(basis_for(when), None) if basis_for else None

        cbot_cost = None
        fees = 0.0
        if import_fees_for is not None:
            fees = to_float(import_fees_for(draw), None)
        if None not in (board, rate, basis, fees) and factor:
            cbot_cost = (board + basis) * factor * rate + fees
        effects = {"imp_cbot": None, "imp_basis": None, "imp_fx": None}
        terms = import_terms_for(draw) if import_terms_for is not None else None
        if terms and cbot_cost is not None and cost is not None:
            cif, cost_fx, premium = (to_float(x, None) for x in terms)
            if None not in (cif, cost_fx, premium) and premium != 0:
                fixing = cif / factor - premium
                effects = {"imp_cbot": factor * rate * (board - fixing),
                           "imp_basis": factor * rate * (basis - premium),
                           "imp_fx": cif * (rate - cost_fx)}

        row = dict(draw)
        row.update({
            "local_egp_mt": local, "local_price_date":
                local_date.isoformat() if local_date else "",
            "local_key": local_key,
            "cbot": board, "fx": rate, "basis": basis,
            "cbot_egp_mt": cbot_cost,
            "import_fees_egp_mt": fees if cbot_cost is not None else None,
            "imp_cbot_egp_mt": effects["imp_cbot"],
            "imp_basis_egp_mt": effects["imp_basis"],
            "imp_fx_egp_mt": effects["imp_fx"],
            "saving_vs_local_egp_mt":
                (local - cost) if None not in (local, cost) else None,
            "saving_vs_cbot_egp_mt":
                (cbot_cost - cost) if None not in (cbot_cost, cost) else None,
            "stale": max([a for a in (local_age, board_age, fx_age)
                          if a is not None], default=None),
            "local_at_delivery_egp_mt": local_del,
        })
        # Split only where all three prices exist, so that on every split
        # tonne purchase + timing is exactly the saving on the day of use.
        split = None not in (cost, local, local_del)
        row["purchase_effect_egp_mt"] = (local_del - cost) if split else None
        row["timing_effect_egp_mt"] = (local - local_del) if split else None
        row["is_stale"] = (row["stale"] is not None and row["stale"] > stale_days)
        for key in ("saving_vs_local", "saving_vs_cbot", "purchase_effect",
                    "timing_effect", "imp_cbot", "imp_basis", "imp_fx"):
            per_mt = row[key + "_egp_mt"]
            row[key + "_egp"] = (per_mt * draw["mt"]) if per_mt is not None else None
        row["cost_egp"] = (cost * draw["mt"]) if cost is not None else None
        rows.append(row)
    return rows


def _totals(rows):
    mt = sum(r["mt"] for r in rows)
    out = {"mt": mt, "draws": len(rows),
           "stale_mt": sum(r["mt"] for r in rows if r.get("is_stale")),
           "estimated_mt": sum(r["mt"] for r in rows
                               if r.get("kind") == "estimated")}
    out["logged_mt"] = mt - out["estimated_mt"]
    for key in ("cost", "saving_vs_local", "saving_vs_cbot", "purchase_effect",
                "timing_effect", "imp_cbot", "imp_basis", "imp_fx"):
        total = sum(r[key + "_egp"] for r in rows if r.get(key + "_egp") is not None)
        priced = sum(r["mt"] for r in rows if r.get(key + "_egp") is not None)
        out[key + "_egp"] = total
        out[key + "_mt_priced"] = priced
        # Weighted by the tonnes actually priced, not by every tonne drawn:
        # dividing by the full quantity would quietly dilute the average
        # with rows that could not be valued at all.
        out[key + "_egp_mt"] = (total / priced) if priced else None
    # What could not be split (no local price on the delivery day) is kept
    # as its own line, so the bridge always closes on the headline saving.
    out["unsplit_egp"] = (out["saving_vs_local_egp"] - out["purchase_effect_egp"]
                          - out["timing_effect_egp"])
    # The same for the import comparison: board + basis + FX, and the rest.
    out["imp_unsplit_egp"] = (out["saving_vs_cbot_egp"] - out["imp_cbot_egp"]
                              - out["imp_basis_egp"] - out["imp_fx_egp"])
    return out


def savings_report(lots, events, commodity=None, start=None, end=None,
                   local_series=None, cbot_series=None, fx_series=None,
                   basis_for=None, factor=0.3937,
                   stale_days=DEFAULT_STALE_DAYS, origin=None, draws=None,
                   local_lookup=None, import_fees_for=None, import_terms_for=None):
    """Draws, the same rolled up by day, cargo and origin, and the totals.

    ``draws`` takes the withdrawals from the inventory walk (see
    draws_from_inventory); without it the logged events are walked here,
    which knows nothing of estimates or stock counts.
    """
    if draws is None:
        everything = consumption_draws(lots, events, commodity, None, None, origin)
    else:
        everything = list(draws)
    counted_mt = sum(d["mt"] for d in everything if d.get("kind") == "count")
    # Tonnes cleared by a stock count have no consumption day, and a saving
    # judged "on the day consumed" cannot be judged without one.
    draws = within([d for d in everything if d.get("kind") != "count"],
                   start, end)
    rows = value_draws(draws, local_series, cbot_series, fx_series,
                       basis_for, factor, stale_days, local_lookup,
                       import_fees_for=import_fees_for, import_terms_for=import_terms_for)

    by_day, by_contract, by_origin = {}, {}, {}
    for row in rows:
        for bucket, key in ((by_day, row["date"].isoformat()),
                            (by_contract, row.get("contract_ref") or "(unsourced)"),
                            (by_origin, row.get("origin") or "(no origin)")):
            bucket.setdefault(key, []).append(row)

    return {
        "rows": rows,
        "by_day": [{"key": k, "rows": v, **_totals(v)}
                   for k, v in sorted(by_day.items())],
        "by_contract": [{"key": k, "rows": v, **_totals(v)}
                        for k, v in sorted(by_contract.items())],
        "by_origin": [{"key": k, "rows": v, **_totals(v)}
                      for k, v in sorted(by_origin.items())],
        "totals": _totals(rows),
        "coverage": cargo_coverage(lots, everything, commodity, start, end,
                                   origin),
        "counted_mt": counted_mt,
        "version": CONSUMPTION_SAVINGS_VERSION,
    }

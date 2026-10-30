"""Did the contract save money, judged tonne by tonne as it was eaten.

The savings already in the app answer narrower questions. The Savings
Tracker values a closed cargo at one date, which ignores that it is
consumed over months while the market moves underneath it. Inventory vs
Market values what is still in the yard at today's prices, and says
nothing about the tonnes already burned.

This values every tonne on the day it was actually consumed, against two
alternatives available that day:

    vs local   consumed_mt x (local price that day        - what it cost)
    vs CBOT    consumed_mt x (board + basis, converted    - what it cost)

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

CONSUMPTION_SAVINGS_VERSION = "1.0"

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
                     commodity=None, extra=None):
    """A ``{date: value}`` map from logged rows, newest wins per date.

    ``extra`` names a second field added to the first, which is how a local
    price plus its transport becomes one all-in figure without the caller
    having to pre-flatten the rows.
    """
    out = {}
    want = _base(commodity) if commodity else None
    for row in rows or []:
        if want and _base(row.get("commodity")) != want:
            continue
        date = _date(row.get(date_key))
        value = to_float(row.get(value_key), None)
        if date is None or value is None:
            continue
        if extra:
            value += to_float(row.get(extra), 0.0) or 0.0
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
    first, last = _date(start), _date(end)

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
            "date": landed, "left": qty, "base": base,
            "cost": to_float(lot.get("cost_egp_mt"), None),
            "lot_id": lot.get("lot_id") or lot.get("contract_id") or "",
            "ref": (lot.get("contract_ref") or lot.get("name")
                    or lot.get("contract_id") or "").strip(),
            "origin": _origin(lot),
            "supplier": (lot.get("supplier") or "").strip(),
        })
    layers.sort(key=lambda x: (x["date"], str(x["lot_id"])))

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
    if first or last:
        draws = [d for d in draws
                 if (not first or d["date"] >= first)
                 and (not last or d["date"] <= last)]
    return draws


def value_draws(draws, local_series=None, cbot_series=None, fx_series=None,
                basis_for: Callable[[dt.date], Any] | None = None,
                factor=0.3937, stale_days=DEFAULT_STALE_DAYS):
    """Price each draw against what that day's alternatives would have cost.

    A positive saving means the tonne cost less than the alternative, which
    is the direction a reader expects from the word.
    """
    rows = []
    for draw in draws or []:
        when = draw["date"]
        cost = to_float(draw.get("cost_egp_mt"), None)
        local, local_date, local_age = nearest_on_or_before(local_series, when)
        board, board_date, board_age = nearest_on_or_before(cbot_series, when)
        rate, fx_date, fx_age = nearest_on_or_before(fx_series, when)
        basis = to_float(basis_for(when), None) if basis_for else None

        cbot_cost = None
        if None not in (board, rate, basis) and factor:
            cbot_cost = (board + basis) * factor * rate

        row = dict(draw)
        row.update({
            "local_egp_mt": local, "local_price_date":
                local_date.isoformat() if local_date else "",
            "cbot": board, "fx": rate, "basis": basis,
            "cbot_egp_mt": cbot_cost,
            "saving_vs_local_egp_mt":
                (local - cost) if None not in (local, cost) else None,
            "saving_vs_cbot_egp_mt":
                (cbot_cost - cost) if None not in (cbot_cost, cost) else None,
            "stale": max([a for a in (local_age, board_age, fx_age)
                          if a is not None], default=None),
        })
        row["is_stale"] = (row["stale"] is not None and row["stale"] > stale_days)
        for key in ("saving_vs_local", "saving_vs_cbot"):
            per_mt = row[key + "_egp_mt"]
            row[key + "_egp"] = (per_mt * draw["mt"]) if per_mt is not None else None
        row["cost_egp"] = (cost * draw["mt"]) if cost is not None else None
        rows.append(row)
    return rows


def _totals(rows):
    mt = sum(r["mt"] for r in rows)
    out = {"mt": mt, "draws": len(rows),
           "stale_mt": sum(r["mt"] for r in rows if r.get("is_stale"))}
    for key in ("cost", "saving_vs_local", "saving_vs_cbot"):
        total = sum(r[key + "_egp"] for r in rows if r.get(key + "_egp") is not None)
        priced = sum(r["mt"] for r in rows if r.get(key + "_egp") is not None)
        out[key + "_egp"] = total
        out[key + "_mt_priced"] = priced
        # Weighted by the tonnes actually priced, not by every tonne drawn:
        # dividing by the full quantity would quietly dilute the average
        # with rows that could not be valued at all.
        out[key + "_egp_mt"] = (total / priced) if priced else None
    return out


def savings_report(lots, events, commodity=None, start=None, end=None,
                   local_series=None, cbot_series=None, fx_series=None,
                   basis_for=None, factor=0.3937,
                   stale_days=DEFAULT_STALE_DAYS, origin=None):
    """Draws, the same rolled up by day, cargo and origin, and the totals."""
    draws = consumption_draws(lots, events, commodity, start, end, origin)
    rows = value_draws(draws, local_series, cbot_series, fx_series,
                       basis_for, factor, stale_days)

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
        "version": CONSUMPTION_SAVINGS_VERSION,
    }

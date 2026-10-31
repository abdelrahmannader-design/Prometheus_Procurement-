"""Management procurement savings report — the data model.

Five questions, each answered only from records that can be traced:

1. Historical savings: every consumed tonne allocated to a real contract,
   valued at the local market price observed on (or carried forward to)
   the day it was consumed, against the contract's landed cost.
2. Open contracts: what is not yet consumed, at today's local price —
   fixed-price contracts apart from unpriced (indicative) ones.
3. The CBOT each contract was fixed at — recorded pricing lots, or implied
   from final CIF ÷ factor − premium when no pricing date is stored.
4. The CBOT on each consumption day, compared only where the stored
   series is on the contract's own futures month.
5. Rankings and data quality, with every exclusion listed and a set of
   validation checks that decide whether the report is management-ready.

Nothing is filled in: a missing price, an unsourced tonne or an
unmatched futures month is excluded and disclosed, never valued at zero
or at an assumed constant.

Pure functions only — the app gathers the inputs, this builds the model
both the Excel and the HTML exports render.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from collections import defaultdict

from .timing_report import Series

MGMT_REPORT_VERSION = "2.0"

FACTORS = {"CORN": 0.3937, "SOYBEAN": 0.36745, "WHEAT": 0.36745, "SBM": 1.1023}
UNITS = {"CORN": "¢/bu", "SOYBEAN": "¢/bu", "WHEAT": "¢/bu", "SBM": "$/short ton"}
PLAUSIBLE = {"CORN": (250.0, 900.0), "SOYBEAN": (700.0, 1900.0),
             "WHEAT": (350.0, 1300.0), "SBM": (200.0, 650.0)}
# Listed CBOT contract months per commodity.
CONTRACT_MONTHS = {"CORN": (3, 5, 7, 9, 12), "WHEAT": (3, 5, 7, 9, 12),
                   "SOYBEAN": (1, 3, 5, 7, 8, 9, 11), "SBM": (1, 3, 5, 7, 8, 9, 10, 12)}
MONTH_CODES = {1: "F", 3: "H", 5: "K", 7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z"}
MONTH_NAMES = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6, "JUL": 7,
               "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}
CODE_MONTHS = {v: k for k, v in MONTH_CODES.items()}

DEFAULTS = {
    "carry_days": 7,        # a local quote up to this old is "carried forward"
    "max_carry_days": 30,   # older than this, the comparison is excluded
    "cbot_max_age_days": 7, # a CBOT print older than this is not used
    "neutral_cbot": 1.0,    # |CBOT difference| below this (price units) is Neutral
    "year_lookback_days": 75,
    "market_before_days": 150,  # an implied fixing must lie within the stored market range
    "market_after_days": 120,   # from this many days before delivery to this many after
    "market_margin": 0.10,      # widened by this share either side
}

REALIZED = "Final CIF"
PROVISIONAL = "Provisional CIF"
FIFO = "FIFO Estimated"
ACTUAL = "Actual"
MATCHED = "Month-matched"


def _d(value):
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _n(value):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if v == v and v not in (float("inf"), float("-inf")) else None


def _s(rows, fn):
    return sum(v for v in (fn(r) for r in rows) if isinstance(v, (int, float)))


# ── 1. futures calendar ──────────────────────────────────────────────────

def _business_back(day):
    while day.weekday() >= 5:
        day -= dt.timedelta(days=1)
    return day


def last_trade_day(year, month):
    """CBOT grains and meal: the business day before the 15th."""
    return _business_back(dt.date(year, month, 15) - dt.timedelta(days=1))


def first_notice_day(year, month):
    """The last business day of the month before the contract month."""
    return _business_back(dt.date(year, month, 1) - dt.timedelta(days=1))


def parse_futures_month(label):
    """('DEC'|'MAY-26'|'Sep'|'March'|'Z26'|'DEC 2026') → (month, year or None)."""
    text = str(label or "").strip().upper()
    if not text:
        return None
    m = re.fullmatch(r"([FGHJKMNQUVXZ])\s*(\d{2}|\d{4})", text)
    if m:
        year = int(m.group(2))
        return CODE_MONTHS.get(m.group(1)), (year + 2000 if year < 100 else year)
    m = re.match(r"([A-Z]{3})[A-Z]*[\s\-/']*(\d{2}|\d{4})?$", text)
    if not m or m.group(1) not in MONTH_NAMES:
        return None
    year = m.group(2)
    year = (int(year) + 2000 if len(year) == 2 else int(year)) if year else None
    return MONTH_NAMES[m.group(1)], year


def resolve_contract_month(label, base, reference, lookback_days=DEFAULTS["year_lookback_days"]):
    """The futures contract a record names, with its year.

    A label without a year takes the first year whose contract was still
    trading ``lookback_days`` before the reference date (pricing date, else
    delivery) — and says the year was inferred.
    """
    parsed = parse_futures_month(label)
    months = CONTRACT_MONTHS.get(base)
    if not parsed or not months or parsed[0] not in months:
        return None
    month, year = parsed
    inferred = year is None
    if inferred:
        ref = _d(reference)
        if ref is None:
            return None
        floor = ref - dt.timedelta(days=lookback_days)
        year = next(y for y in range(ref.year - 1, ref.year + 3)
                    if last_trade_day(y, month) >= floor)
    name = [k for k, v in MONTH_NAMES.items() if v == month][0]
    return {"year": year, "month": month, "code": f"{name}-{year % 100:02d}",
            "ticker": f"{MONTH_CODES.get(month, '?')}{year % 100:02d}", "inferred": inferred,
            "last_trade": last_trade_day(year, month).isoformat()}


def _front(day, base, by):
    months = CONTRACT_MONTHS[base]
    for year in range(day.year, day.year + 2):
        for month in months:
            edge = last_trade_day(year, month) if by == "expiry" else first_notice_day(year, month)
            if (edge >= day) if by == "expiry" else (edge > day):
                return year, month
    return None


def benchmark_status(day, base, contract_month):
    """Is the stored front-month CBOT series on the contract's own month that day?

    The series is a continuous front month with no month recorded on it,
    so it is matched by calendar: the day must fall where the front month
    is the contract's month under both common roll conventions (at first
    notice and at expiry). Days between them are a roll window and are not
    compared; neither are days on another contract month.
    """
    if contract_month is None:
        return "No futures month recorded", False
    if base not in CONTRACT_MONTHS:
        return "No futures calendar for commodity", False
    want = (contract_month["year"], contract_month["month"])
    by_exp, by_fnd = _front(day, base, "expiry"), _front(day, base, "fnd")
    if by_exp == want and by_fnd == want:
        return MATCHED, True
    if by_exp == want or by_fnd == want:
        return "Roll window — series may be on the next month", False
    if day > last_trade_day(*want):
        return f"Contract month {contract_month['code']} expired — no month-specific data", False
    return f"Series on an earlier month ({_label(by_exp)}) — not comparable", False


def _label(ym):
    if not ym:
        return "?"
    name = [k for k, v in MONTH_NAMES.items() if v == ym[1]][0]
    return f"{name}-{ym[0] % 100:02d}"


# ── 2. the CBOT a contract was fixed at ──────────────────────────────────

def fixing(contract):
    """Recorded, implied or not fixed — never a final number for an unpriced CIF.

    ``contract`` carries base, qty_mt, cif_usd_mt, premium, premium_label,
    pricing_status (PRICED / PARTIAL / UNPRICED), pricing_lots and
    pricing_date.
    """
    c = contract
    base = c.get("base")
    factor, unit = FACTORS.get(base), UNITS.get(base, "")
    out = {"type": "", "status": "", "value": None, "indicative": None, "unit": unit,
           "factor": factor, "eligible": False, "fixed": False, "note": "",
           "pricing_date": c.get("pricing_date") or "", "lot_mt": 0.0,
           "pricing_date_known": bool(c.get("pricing_date"))}
    if factor is None:
        out.update(status="Not eligible — no CBOT conversion for this commodity")
        return out
    qty = _n(c.get("qty_mt")) or 0.0
    lots = [x for x in (c.get("pricing_lots") or [])
            if isinstance(x, dict) and _n(x.get("qty_mt")) and _n(x.get("cbot")) is not None]
    premium = _n(c.get("premium"))
    label = str(c.get("premium_label") or "").upper()
    if not lots and ("FLAT" in label or not premium):
        out.update(status="Flat price — no CBOT component", type="Flat price")
        return out
    out["eligible"] = True
    cif = _n(c.get("cif_usd_mt"))
    pricing = (c.get("pricing_status") or "").upper()
    lo, hi = PLAUSIBLE.get(base, (None, None))
    if lots:
        mt = sum(_n(x["qty_mt"]) for x in lots)
        value = sum(_n(x["qty_mt"]) * _n(x["cbot"]) for x in lots) / mt
        dates = sorted(str(x.get("date") or "")[:10] for x in lots if x.get("date"))
        out.update(type="Recorded", value=value, fixed=True, lot_mt=mt, pricing_date_known=bool(dates),
                   pricing_date=(f"{dates[0]} – {dates[-1]}" if len(dates) > 1 else (dates[0] if dates else "")))
        share = (mt / qty) if qty else 1.0
        if share >= 0.995:
            out["status"] = "Recorded — pricing lots"
        else:
            out["status"] = f"Recorded — pricing lots for {mt:,.0f} of {qty:,.0f} MT"
            out["note"] = ("The rest is not yet priced; the fixing shown is the lots' weighted CBOT."
                           if pricing == "PARTIAL" else
                           "The rest is not recorded as lots; the lots' weighted CBOT is used for it.")
        prems = {round(_n(x.get("premium_cents")) or 0, 2) for x in lots if _n(x.get("premium_cents")) is not None}
        if premium is not None and prems and prems != {round(premium, 2)}:
            out["note"] = (out["note"] + " " if out["note"] else "") + "Lot premiums differ from the contract premium."
        return out
    if cif is None:
        out.update(status="Not assessable — no CIF recorded", type="Missing CIF")
        return out
    implied = cif / factor - premium
    if pricing != "PRICED":
        out.update(type="Not fixed", status="Not fixed — unpriced; CIF is provisional",
                   indicative=implied)
        return out
    if lo is not None and not (lo <= implied <= hi):
        out.update(type="Check premium units", indicative=implied,
                   status=f"Not assessable — implied {implied:,.1f} {unit} is outside "
                          f"{lo:,.0f}–{hi:,.0f}; check the premium's units")
        return out
    out.update(type="Implied", value=implied, fixed=True,
               status="Implied — CIF ÷ factor − premium"
               + ("" if out["pricing_date_known"] else " (pricing date not recorded)"))
    return out


def market_check(fix, history, delivery, opts=DEFAULTS):
    """An implied fixing the stored market never traded near is a data problem.

    Recorded lots are what was actually traded and are not second-guessed.
    """
    if not fix.get("fixed") or fix.get("type") != "Implied" or history is None or not len(history):
        return ""
    end = _d(delivery)
    if end is None:
        return ""
    lo_d = end - dt.timedelta(days=opts["market_before_days"])
    hi_d = end + dt.timedelta(days=opts["market_after_days"])
    vals = [v for d, v in zip(history.dates, history.values) if lo_d <= d <= hi_d]
    if len(vals) < 10:
        return ""
    lo, hi = min(vals) * (1 - opts["market_margin"]), max(vals) * (1 + opts["market_margin"])
    if lo <= fix["value"] <= hi:
        return ""
    return (f"Not assessable — implied {fix['value']:,.1f} {fix['unit']} is outside the stored market range "
            f"{min(vals):,.0f}–{max(vals):,.0f} around delivery; check the CIF and premium units")


# ── 3. building the model ────────────────────────────────────────────────

def _local_status(age, opts):
    if age is None:
        return None, "No local price observation on or before the day"
    if age > opts["max_carry_days"]:
        return None, f"Local quote {age} days old — older than {opts['max_carry_days']} days"
    if age == 0:
        return "Same-day observation", ""
    if age <= opts["carry_days"]:
        return f"Carried forward ({age} d)", ""
    return f"Stale — carried forward ({age} d)", ""


def build(inp, **overrides):
    """The whole management model from the app's gathered inputs.

    ``inp`` keys: as_of, generated, app, contracts, local_purchases, draws,
    local_obs, cbot ({base: [(date, price)]}), spike_pct, ignored_entries,
    stock_checks, dropped, look_alikes, rates, walk_mode.
    """
    opts = dict(DEFAULTS, **overrides)
    as_of = _d(inp["as_of"])
    contracts = {c["id"]: dict(c) for c in inp["contracts"]}
    lp = {p["lot_id"]: p for p in inp.get("local_purchases") or []}
    obs_index = {(o["key"], o["date"]): o for o in inp.get("local_obs") or []}
    series, spikes = {}, {}
    for base, pairs in (inp.get("cbot") or {}).items():
        series[base] = Series(pairs)
        spikes[base] = series[base].spikes(inp.get("spike_pct", 2.5)) if len(series[base]) > 2 else set()

    excluded = []

    def exclude(category, reason, **kw):
        excluded.append(dict({"category": category, "reason": reason, "date": "", "contract": "",
                              "contract_id": "", "commodity": "", "mt": None, "source": ""}, **kw))

    for c in contracts.values():
        c["fix"] = fixing(c)
        c["contract_month"] = resolve_contract_month(
            c.get("futures_month"), c["base"], c.get("pricing_date") or c.get("delivery_date"))
        flag = market_check(c["fix"], series.get(c["base"]), c.get("delivery_date"), opts)
        if flag:
            c["fix"].update(fixed=False, indicative=c["fix"]["value"], value=None,
                            type="Check CIF / premium", status=flag)

    # ── allocations: every consumed tonne, attributed or excluded ────────
    allocations, by_contract = [], defaultdict(list)
    consumed_total = defaultdict(float)
    for d in sorted(inp.get("draws") or [], key=lambda x: (str(x["date"]), str(x.get("lot_id")))):
        day, mt, base = _d(d["date"]), _n(d["mt"]) or 0.0, d.get("base") or ""
        consumed_total[base] += mt
        lot = str(d.get("lot_id") or "")
        if d.get("kind") == "count":
            exclude("Cleared by stock count", "Removed by a physical stock count; it has no consumption "
                    "day, so it cannot be valued against that day's prices.",
                    date=day.isoformat(), commodity=base, mt=mt, source=lot or "stock count")
            continue
        if lot.startswith("CONTRACT-") and lot[9:] in contracts:
            c = contracts[lot[9:]]
            row = {"type": "Import", "contract_id": c["id"], "contract": c["contract"],
                   "supplier": c.get("supplier", ""), "commodity": c.get("commodity", ""),
                   "base": c["base"], "origin": c.get("origin", ""), "source_id": c.get("source_id", "")}
        elif lot in lp:
            p = lp[lot]
            row = {"type": "Local purchase", "contract_id": lot, "contract": p.get("ref") or lot,
                   "supplier": p.get("supplier", ""), "commodity": p.get("commodity", ""),
                   "base": base, "origin": "Local", "source_id": p.get("source_id", "")}
        else:
            exclude("Unsourced consumption",
                    "Consumption at the daily rate on a day with no recorded cargo or local purchase "
                    "in stock. No source record — not allocated, not valued.",
                    date=day.isoformat(), commodity=base, mt=mt, source=lot or "(none)")
            continue
        row.update(date=day.isoformat(), mt=mt,
                   method=ACTUAL if d.get("kind") == "logged" else FIFO,
                   assumption=d.get("assumption") or "", local=d.get("local") or {})
        allocations.append(row)
        by_contract[row["contract_id"]].append(row)

    for cid, rows in by_contract.items():
        c = contracts.get(cid)
        start = (_n(c.get("qty_mt")) if c else _n(lp[cid].get("qty_mt"))) or 0.0
        run = 0.0
        for r in rows:
            run += r["mt"]
            r["remaining_mt"] = start - run

    # ── savings vs local, one row per import allocation ──────────────────
    savings_rows = []
    for r in allocations:
        if r["type"] != "Import":
            continue
        c = contracts[r["contract_id"]]
        cost = _n(c.get("landed_egp_mt"))
        loc = r["local"]
        price, obs_date = _n(loc.get("price")), _d(loc.get("date"))
        age = (_d(r["date"]) - obs_date).days if obs_date else None
        status, why = _local_status(age, opts)
        base_row = {k: r[k] for k in ("date", "contract_id", "contract", "supplier", "commodity",
                                      "base", "origin", "mt", "method")}
        if cost is None:
            exclude("No landed cost", "The contract has no CIF, so it has no landed cost to compare.",
                    date=r["date"], contract=c["contract"], contract_id=c["id"], commodity=c["base"],
                    mt=r["mt"], source=c.get("source_id", ""))
            continue
        if status is None:
            exclude("No usable local price", why, date=r["date"], contract=c["contract"],
                    contract_id=c["id"], commodity=c["base"], mt=r["mt"],
                    source=f"local key {loc.get('key') or '—'}")
            continue
        o = obs_index.get((loc.get("key"), obs_date.isoformat()), {})
        basis = REALIZED if c.get("cif_final") else PROVISIONAL
        savings_rows.append(dict(base_row, cost=cost, local=price, local_date=obs_date.isoformat(),
                                 local_age=age, local_key=loc.get("key", ""),
                                 local_source=o.get("source_id", ""), local_status=status,
                                 cif_basis=basis, saving_mt=price - cost,
                                 saving=(price - cost) * r["mt"],
                                 quality=f"{r['method']} · {status} · {basis}"))

    # ── CBOT on each consumption day vs the contract's fixing ────────────
    cbot_rows = []
    for r in allocations:
        if r["type"] != "Import":
            continue
        c = contracts[r["contract_id"]]
        f = c["fix"]
        if not f["eligible"]:
            continue
        if not f["fixed"]:
            continue
        day = _d(r["date"])
        hist, spk = series.get(c["base"]), spikes.get(c["base"], set())
        price, pdate = (None, None)
        if hist is not None and len(hist):
            price, pdate = hist.on_or_before(day)
            while pdate is not None and pdate in spk:
                price, pdate = hist.on_or_before(pdate - dt.timedelta(days=1))
        status, ok = benchmark_status(day, c["base"], c["contract_month"])
        if price is None:
            status, ok = "No stored CBOT on or before the day", False
        elif (day - pdate).days > opts["cbot_max_age_days"]:
            status, ok = f"Latest stored CBOT is {(day - pdate).days} days old", False
        diff = (price - f["value"]) if price is not None else None
        usd_mt = diff * f["factor"] if diff is not None else None
        fx = _n(c.get("fx"))
        result = "Not assessable"
        if ok:
            result = ("Advantage" if diff >= opts["neutral_cbot"] else
                      "Missed opportunity" if diff <= -opts["neutral_cbot"] else "Neutral")
        cbot_rows.append({
            "date": r["date"], "contract_id": c["id"], "contract": c["contract"],
            "supplier": c.get("supplier", ""), "commodity": c.get("commodity", ""), "base": c["base"],
            "mt": r["mt"], "cif": _n(c.get("cif_usd_mt")), "premium": _n(c.get("premium")),
            "unit": f["unit"], "factor": f["factor"], "fix": f["value"], "fix_type": f["type"],
            "futures": (c["contract_month"] or {}).get("code", ""),
            "cbot": price, "cbot_date": pdate.isoformat() if pdate else "",
            "diff": diff if ok else None, "usd_mt": usd_mt if ok else None,
            "usd": usd_mt * r["mt"] if ok else None,
            "egp": usd_mt * r["mt"] * fx if (ok and fx) else None, "fx": fx,
            "proxy_diff": diff, "result": result, "benchmark": status, "assessable": ok,
            "spike_skipped": bool(pdate and day != pdate and any(day >= s > pdate for s in spk)),
        })
        if not ok:
            exclude("CBOT comparison not assessable", status, date=r["date"], contract=c["contract"],
                    contract_id=c["id"], commodity=c["base"], mt=r["mt"],
                    source=f"futures {(c['contract_month'] or {}).get('code', '—')}")

    # ── per contract ──────────────────────────────────────────────────────
    sav_by = defaultdict(list)
    for s in savings_rows:
        sav_by[s["contract_id"]].append(s)
    cb_by = defaultdict(list)
    for s in cbot_rows:
        cb_by[s["contract_id"]].append(s)
    stock = inp.get("stock_by_contract") or {}
    master = []
    for c in sorted(contracts.values(), key=lambda x: (x.get("delivery_date") or "", x["id"])):
        rows = by_contract.get(c["id"], [])
        consumed = _s(rows, lambda r: r["mt"])
        qty = _n(c.get("qty_mt")) or 0.0
        dl = _d(c.get("delivery_date"))
        if dl is None or dl > as_of:
            delivered, delivery = 0.0, (f"Not yet delivered (due {c.get('delivery_date')})"
                                        if dl else "No delivery date — reconcile")
            verified = dl is not None
        elif c.get("receipt_logged"):
            delivered, delivery, verified = qty, "Delivered — receipt logged", True
        elif c.get("storage_start"):
            delivered, delivery, verified = qty, "Delivered — storage start recorded", True
        else:
            delivered, delivery, verified = qty, "Delivery not verified — reconcile", False
        avail = _n(stock.get(c["id"])) or 0.0
        sr = sav_by.get(c["id"], [])
        smt = _s(sr, lambda r: r["mt"])
        sv = _s(sr, lambda r: r["saving"])
        lc = _s(sr, lambda r: r["local"] * r["mt"])
        cr = cb_by.get(c["id"], [])
        amt = _s([x for x in cr if x["assessable"]], lambda r: r["mt"])
        adv = _s([x for x in cr if x["assessable"]], lambda r: r["usd"])
        c.update({
            "delivered_mt": delivered, "outstanding_mt": qty - delivered, "consumed_mt": consumed,
            "available_mt": avail, "delivery_status": delivery, "delivery_verified": verified,
            "unreconciled_mt": round(delivered - consumed - avail, 6) if delivered else round(-consumed - avail, 6),
            "first_date": rows[0]["date"] if rows else "", "last_date": rows[-1]["date"] if rows else "",
            "hist": {"priced_mt": smt, "saving": sv if sr else None,
                     "saving_mt": (sv / smt) if smt else None,
                     "local_wavg": (lc / smt) if smt else None,
                     "saving_pct": (sv / lc * 100) if lc else None,
                     "excluded_mt": consumed - smt},
            "cbot": {"consumed_mt": _s(cr, lambda r: r["mt"]), "assessed_mt": amt,
                     "coverage": (amt / _s(cr, lambda r: r["mt"])) if cr and _s(cr, lambda r: r["mt"]) else None,
                     "avg_cbot": (_s([x for x in cr if x["assessable"]], lambda r: r["cbot"] * r["mt"]) / amt) if amt else None,
                     "usd": adv if amt else None,
                     "egp": _s([x for x in cr if x["assessable"]], lambda r: r["egp"]) if amt else None,
                     "advantage_usd": _s([x for x in cr if x["assessable"] and x["usd"] > 0], lambda r: r["usd"]),
                     "missed_usd": _s([x for x in cr if x["assessable"] and x["usd"] < 0], lambda r: r["usd"])},
        })
        cb = c["cbot"]
        cb["diff"] = (cb["avg_cbot"] - c["fix"]["value"]) if cb["avg_cbot"] is not None else None
        cb["usd_mt"] = (cb["diff"] * c["fix"]["factor"]) if cb["diff"] is not None else None
        cb["assessment"] = (
            "Not fixed" if c["fix"]["eligible"] and not c["fix"]["fixed"] else
            "Not eligible" if not c["fix"]["eligible"] else
            "Not consumed" if not cr else
            "Not assessable" if not amt else
            ("Advantage" if cb["diff"] >= opts["neutral_cbot"] else
             "Missed opportunity" if cb["diff"] <= -opts["neutral_cbot"] else "Neutral"))
        c["assessment"] = assessment(c)
        master.append(c)
        if c["fix"]["eligible"] and not c["fix"]["fixed"] and consumed:
            exclude("Contract not fixed", c["fix"]["status"], contract=c["contract"], contract_id=c["id"],
                    commodity=c["base"], mt=consumed, source=c.get("source_id", ""))
        if not verified and dl is not None and dl <= as_of:
            exclude("Delivery not verified", "Delivery date passed but no receipt or storage start is "
                    "recorded; left out of the confirmed open totals.", contract=c["contract"],
                    contract_id=c["id"], commodity=c["base"], mt=qty, source=c.get("source_id", ""))

    # ── open contracts vs local today ─────────────────────────────────────
    open_rows = []
    for c in master:
        unconsumed = c["available_mt"] + c["outstanding_mt"]
        if not (c.get("is_open") or c["available_mt"] > 1e-6):
            continue
        local, landed = _n(c.get("local_today")), _n(c.get("landed_today"))
        per = (local - landed) if None not in (local, landed) else None
        fixed = (c.get("pricing_status") or "").upper() == "PRICED" and c.get("cif_final")
        if per is None:
            cls = "Not assessable"
        elif not c["delivery_verified"] and c["outstanding_mt"] == 0:
            cls = "Reconcile delivery"
        else:
            cls = "Fixed price" if fixed else "Indicative (unpriced)"
        open_rows.append({
            "contract_id": c["id"], "contract": c["contract"], "supplier": c.get("supplier", ""),
            "commodity": c.get("commodity", ""), "base": c["base"], "status": c.get("status", ""),
            "is_open": bool(c.get("is_open")), "qty_mt": c.get("qty_mt"), "delivered_mt": c["delivered_mt"],
            "consumed_mt": c["consumed_mt"], "available_mt": c["available_mt"],
            "outstanding_mt": c["outstanding_mt"], "pricing_status": c.get("pricing_status", ""),
            "cif": _n(c.get("cif_today")), "cif_basis": c.get("cif_basis_today", ""),
            "fx": _n(c.get("fx_today")), "fx_basis": c.get("fx_basis_today", ""),
            "landed": landed, "local": local, "local_date": c.get("local_today_date", ""),
            "local_key": c.get("local_today_key", ""), "saving_mt": per,
            "potential": per * unconsumed if per is not None else None, "unconsumed_mt": unconsumed,
            "class": cls, "delivery_status": c["delivery_status"],
        })

    # ── roll-ups, KPIs, data quality, validation ─────────────────────────
    hist_total = _s(savings_rows, lambda r: r["saving"])
    hist_mt = _s(savings_rows, lambda r: r["mt"])
    assessed = [r for r in cbot_rows if r["assessable"]]
    fixed_open = [r for r in open_rows if r["class"] == "Fixed price"]
    ind_open = [r for r in open_rows if r["class"] == "Indicative (unpriced)"]
    open_c = [c for c in master if c.get("is_open")]
    k = {
        "historical_saving_egp": hist_total, "historical_mt": hist_mt,
        "historical_saving_egp_mt": (hist_total / hist_mt) if hist_mt else None,
        "historical_final_egp": _s([r for r in savings_rows if r["cif_basis"] == REALIZED], lambda r: r["saving"]),
        "historical_provisional_egp": _s([r for r in savings_rows if r["cif_basis"] == PROVISIONAL], lambda r: r["saving"]),
        "open_fixed_potential_egp": _s(fixed_open, lambda r: r["potential"]),
        "open_fixed_mt": _s(fixed_open, lambda r: r["unconsumed_mt"]),
        "open_indicative_potential_egp": _s(ind_open, lambda r: r["potential"]),
        "open_indicative_mt": _s(ind_open, lambda r: r["unconsumed_mt"]),
        "open_outstanding_mt": _s([c for c in open_c if c["delivery_verified"]], lambda c: c["outstanding_mt"]),
        "open_available_mt": _s(open_c, lambda c: c["available_mt"]),
        "open_contracts": len(open_c),
        "cbot_advantage_usd": _s([r for r in assessed if r["usd"] > 0], lambda r: r["usd"]),
        "cbot_missed_usd": _s([r for r in assessed if r["usd"] < 0], lambda r: r["usd"]),
        "cbot_net_usd": _s(assessed, lambda r: r["usd"]),
        "cbot_net_egp": _s(assessed, lambda r: r["egp"]),
        "cbot_assessed_mt": _s(assessed, lambda r: r["mt"]),
        "cbot_fixed_consumed_mt": _s(cbot_rows, lambda r: r["mt"]),
        "contracts": len(master),
    }
    k["cbot_coverage"] = (k["cbot_assessed_mt"] / k["cbot_fixed_consumed_mt"]) if k["cbot_fixed_consumed_mt"] else None

    commodities = []
    for base in sorted({c["base"] for c in master}):
        sr = [r for r in savings_rows if r["base"] == base]
        ar = [r for r in assessed if r["base"] == base]
        orr = [r for r in open_rows if r["base"] == base]
        alloc = [r for r in allocations if r["base"] == base]
        exc = _s([e for e in excluded if e["commodity"] == base and e["category"] in
                  ("Unsourced consumption", "Cleared by stock count")], lambda e: e["mt"])
        mt = _s(sr, lambda r: r["mt"])
        commodities.append({
            "base": base, "contracts": sum(1 for c in master if c["base"] == base),
            "consumed_mt": consumed_total.get(base, 0.0),
            "allocated_import_mt": _s([a for a in alloc if a["type"] == "Import"], lambda r: r["mt"]),
            "allocated_local_mt": _s([a for a in alloc if a["type"] != "Import"], lambda r: r["mt"]),
            "excluded_mt": exc, "priced_mt": mt, "saving_egp": _s(sr, lambda r: r["saving"]),
            "saving_egp_mt": (_s(sr, lambda r: r["saving"]) / mt) if mt else None,
            "open_fixed_egp": _s([r for r in orr if r["class"] == "Fixed price"], lambda r: r["potential"]),
            "open_indicative_egp": _s([r for r in orr if r["class"] == "Indicative (unpriced)"], lambda r: r["potential"]),
            "cbot_net_usd": _s(ar, lambda r: r["usd"]), "cbot_assessed_mt": _s(ar, lambda r: r["mt"]),
        })

    quality = {
        "verified_allocations": sum(1 for a in allocations if a["method"] == ACTUAL),
        "fifo_allocations": sum(1 for a in allocations if a["method"] == FIFO),
        "excluded_unsourced": sum(1 for e in excluded if e["category"] == "Unsourced consumption"),
        "excluded_unsourced_mt": _s([e for e in excluded if e["category"] == "Unsourced consumption"], lambda e: e["mt"]),
        "missing_pricing_dates": sum(1 for c in master if c["fix"]["fixed"] and not c["fix"]["pricing_date_known"]),
        "missing_cbot": sum(1 for r in cbot_rows if not r["assessable"]),
        "missing_cbot_mt": _s([r for r in cbot_rows if not r["assessable"]], lambda r: r["mt"]),
        "missing_local": sum(1 for e in excluded if e["category"] == "No usable local price"),
        "missing_local_mt": _s([e for e in excluded if e["category"] == "No usable local price"], lambda e: e["mt"]),
        "stale_local": sum(1 for r in savings_rows if r["local_status"].startswith("Stale")),
        "stale_local_mt": _s([r for r in savings_rows if r["local_status"].startswith("Stale")], lambda r: r["mt"]),
        "carried_local": sum(1 for r in savings_rows if r["local_status"].startswith("Carried")),
        "same_day_local": sum(1 for r in savings_rows if r["local_status"].startswith("Same")),
    }
    for e in inp.get("ignored_entries") or []:
        exclude("Logged entry not used", e["reason"], date=e.get("date", ""), commodity=e.get("commodity", ""),
                mt=e.get("mt"), source=e.get("source", ""))
    for d in inp.get("dropped") or []:
        exclude("Duplicate record dropped", f"Identical to {d['duplicate_of']} in every field but timestamps.",
                contract_id=d["id"], source=f"contracts.{d['id']}")
    for s in inp.get("stock_checks") or []:
        exclude("Stock count vs FIFO model", f"Counted {s['counted']:,.0f} MT on {s['date']}; the daily-rate "
                f"model leaves {s['modelled']:,.0f} MT that day ({s['counted'] - s['modelled']:+,.0f} MT).",
                date=s["date"], commodity=s["base"], mt=s["counted"] - s["modelled"], source="consumption_log count")

    audit = []
    for b in commodities:
        audit.append({"base": b["base"], "consumed_mt": b["consumed_mt"],
                      "allocated_mt": b["allocated_import_mt"] + b["allocated_local_mt"],
                      "excluded_mt": b["excluded_mt"],
                      "difference_mt": b["consumed_mt"] - b["allocated_import_mt"] - b["allocated_local_mt"] - b["excluded_mt"]})

    model = {
        "title": "Procurement Savings — Management Report", "as_of": as_of.isoformat(),
        "generated": inp.get("generated", ""), "app": inp.get("app", ""),
        "version": MGMT_REPORT_VERSION, "walk_mode": inp.get("walk_mode", ""), "rates": inp.get("rates") or {},
        "options": opts, "contracts": [_public(c) for c in master], "allocations": allocations,
        "savings": savings_rows, "cbot": cbot_rows, "open": open_rows, "excluded": excluded,
        "local_obs": inp.get("local_obs") or [], "commodities": commodities, "kpis": k,
        "quality": quality, "audit": audit, "look_alikes": inp.get("look_alikes") or [],
        "sources": inp.get("sources") or {},
    }
    model["validation"] = validate(model)
    model["management_ready"] = all(v["passed"] for v in model["validation"])
    model["checksum"] = checksum(model)
    return model


def assessment(c):
    """Two or three plain sentences a manager can read in one go."""
    h, cb, f = c["hist"], c["cbot"], c["fix"]
    out = []
    if h["saving"] is not None:
        word = "saved" if h["saving"] >= 0 else "cost"
        out.append(f"Against the local price on the days it was consumed, importing {word} "
                   f"EGP {abs(h['saving']):,.0f} ({h['saving_mt']:+,.0f}/MT on {h['priced_mt']:,.0f} MT, "
                   f"FIFO estimated){'' if c.get('cif_final') else ' — provisional, CIF not final'}.")
    elif c["consumed_mt"]:
        out.append(f"{c['consumed_mt']:,.0f} MT consumed, but no comparison could be supported.")
    else:
        out.append("Nothing consumed from this contract yet.")
    if f["fixed"] and cb["usd"] is not None:
        kind = ("a pricing advantage" if cb["usd"] > 0 else "a missed pricing opportunity" if cb["usd"] < 0
                else "no difference")
        out.append(f"CBOT fixed at {f['value']:,.2f} {f['unit']} ({f['type'].lower()}) vs "
                   f"{cb['avg_cbot']:,.2f} on comparable consumption days — {kind} of "
                   f"USD {abs(cb['usd']):,.0f} on {cb['assessed_mt']:,.0f} MT "
                   f"({(cb['coverage'] or 0) * 100:,.0f}% of its consumed tonnes); a historical benchmark, "
                   "not money that was certainly available.")
    elif f["fixed"] and cb["consumed_mt"]:
        out.append(f"CBOT fixed at {f['value']:,.2f} {f['unit']}; no consumption day fell on its own futures "
                   "month in the stored series, so the CBOT comparison is not assessable.")
    elif f["eligible"] and not f["fixed"]:
        out.append(f["status"] + (f" (indicative {f['indicative']:,.2f} {f['unit']})." if f["indicative"] else "."))
    return " ".join(out)


def _public(c):
    out = {k: v for k, v in c.items() if k not in ("pricing_lots",)}
    out["lots"] = [{k: x.get(k) for k in ("lot_id", "date", "qty_mt", "cbot", "premium_cents", "futures_month")}
                   for x in c.get("pricing_lots") or [] if isinstance(x, dict)]
    return out


def checksum(model):
    """A short fingerprint of the headline figures, printed in both exports."""
    k = model["kpis"]
    keys = sorted(k)
    blob = json.dumps([[x, round(k[x], 2) if isinstance(k[x], float) else k[x]] for x in keys])
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


def validate(m):
    """Every check the brief requires; any failure makes the report not management-ready."""
    k, out = m["kpis"], []

    def check(name, passed, detail):
        out.append({"check": name, "passed": bool(passed), "detail": detail})

    contract_ids = {c["id"] for c in m["contracts"]}
    bad = [r for r in m["savings"] if r["contract_id"] not in contract_ids]
    check("No unsourced rows in headline savings", not bad,
          f"{len(m['savings'])} savings rows, all on contract IDs from the database"
          if not bad else f"{len(bad)} rows without a contract")
    s_rows = sum(r["saving"] for r in m["savings"])
    s_con = sum((c["hist"]["saving"] or 0.0) for c in m["contracts"])
    check("Totals reconcile to contract rows",
          abs(s_rows - k["historical_saving_egp"]) < 0.5 and abs(s_con - k["historical_saving_egp"]) < 0.5,
          f"daily rows {s_rows:,.0f} · contracts {s_con:,.0f} · headline {k['historical_saving_egp']:,.0f}")
    no_obs = [r for r in m["savings"] if not r.get("local_source")]
    check("No missing observation replaced by a constant", not no_obs,
          "every local price used is a stored observation (source record shown); no basis or premium "
          "constant is used" if not no_obs else f"{len(no_obs)} rows use a local price with no source record")
    over = [c["id"] for c in m["contracts"] if c["consumed_mt"] > (c.get("qty_mt") or 0) + 1e-6]
    check("No contract quantity allocated more than once", not over,
          "consumed ≤ contract quantity on every contract" if not over else "over-allocated: " + ", ".join(over))
    unrec = [c["id"] for c in m["contracts"] if c["delivered_mt"] and abs(c["unreconciled_mt"]) > 0.01]
    check("Consumed, stock and outstanding separated", not unrec,
          "delivered = consumed + available stock; outstanding = contract − delivered"
          if not unrec else "does not reconcile: " + ", ".join(unrec))
    miss = [c["id"] for c in m["contracts"] if c["fix"]["eligible"] and (c.get("pricing_status") or "").upper() == "PRICED"
            and c.get("cif_usd_mt") is not None and not c["fix"]["fixed"]
            and c["fix"]["type"] not in ("Check CIF / premium", "Check premium units")]
    flagged = [c["id"] for c in m["contracts"] if c["fix"]["type"] in ("Check CIF / premium", "Check premium units")]
    check("Every eligible fixed contract has a CBOT fixing", not miss,
          ("recorded or implied for every priced CBOT + premium contract"
           + (f"; {len(flagged)} held back as implausible (listed with the reason): " + ", ".join(flagged) if flagged else ""))
          if not miss else "missing: " + ", ".join(miss))
    wrong = [c["id"] for c in m["contracts"] if (c.get("pricing_status") or "").upper() == "UNPRICED" and c["fix"]["fixed"]]
    check("No unpriced contract treated as fixed", not wrong,
          "unpriced contracts show Not fixed with an indicative value only" if not wrong else ", ".join(wrong))
    nonmatched = [r for r in m["cbot"] if r["assessable"] and r["benchmark"] != MATCHED]
    check("Consumption-day CBOT from a comparable benchmark", not nonmatched,
          f"{sum(1 for r in m['cbot'] if r['assessable'])} day-rows compared, all on the contract's own futures month"
          if not nonmatched else f"{len(nonmatched)} compared off-month")
    neg = [r for r in m["cbot"] if r["assessable"] and r["usd"] < 0 and r["result"] != "Missed opportunity"
           and abs(r["diff"]) >= m["options"]["neutral_cbot"]]
    check("Negative CBOT results shown as missed opportunities", not neg,
          f"{sum(1 for r in m['cbot'] if r['result'] == 'Missed opportunity')} day-rows labelled Missed opportunity"
          if not neg else f"{len(neg)} negative rows not labelled")
    audit_bad = [a["base"] for a in m["audit"] if abs(a["difference_mt"]) > 0.01]
    check("Consumed = allocated + excluded", not audit_bad,
          "; ".join(f"{a['base']}: {a['consumed_mt']:,.0f} = {a['allocated_mt']:,.0f} + {a['excluded_mt']:,.0f}"
                    for a in m["audit"]) if not audit_bad else "gap in: " + ", ".join(audit_bad))
    cb = sum(r["usd"] for r in m["cbot"] if r["assessable"])
    cb_c = sum((c["cbot"]["usd"] or 0.0) for c in m["contracts"])
    op = sum((r["potential"] or 0.0) for r in m["open"] if r["class"] == "Fixed price")
    check("Every headline KPI traces to its detail rows",
          abs(cb - k["cbot_net_usd"]) < 0.01 and abs(cb_c - k["cbot_net_usd"]) < 0.01
          and abs(op - k["open_fixed_potential_egp"]) < 0.5,
          f"CBOT net {k['cbot_net_usd']:,.0f} USD = daily rows = contract rows; open fixed potential "
          f"{k['open_fixed_potential_egp']:,.0f} EGP = open rows")
    unsupported = [r for r in m["savings"] if r["local_age"] is None or r["local_age"] > m["options"]["max_carry_days"]]
    check("Manager figures exclude unsupported inputs", not unsupported,
          f"local quotes used are at most {m['options']['max_carry_days']} days old; older or missing ones are "
          "listed under Excluded & Missing Data" if not unsupported else f"{len(unsupported)} rows")
    return out

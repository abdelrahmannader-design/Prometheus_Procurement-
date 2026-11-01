"""Management procurement savings report — the data model.

Five questions, each answered only from records that can be traced:

1. Historical savings: every consumed tonne allocated to a real contract,
   valued at the local market price observed on (or carried forward to)
   the day it was consumed, against the contract's landed cost.
2. Open contracts: what is not yet consumed, at today's local price —
   fixed-price contracts apart from unpriced (indicative) ones.
3. The CBOT each contract was fixed at — recorded pricing lots, or implied
   from final CIF ÷ factor − premium when no pricing date is stored.
4. The CBOT stored for each consumption day (the app's daily CBOT
   series, whatever month it was on that day — the contract's futures
   month is the month its premium is quoted over, not the benchmark).
5. Rankings and data quality, with every exclusion listed and a set of
   validation checks that decide whether the report is management-ready.

Nothing is filled in: a missing price, an unsourced tonne or an
day without a stored CBOT is excluded and disclosed, never valued at zero
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
    "carry_days": 5,        # a local price older than this is highlighted STALE (still in force)
    "max_carry_days": None, # None: no limit — no new local price means the price had not changed
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
MATCHED = "Consumption-day CBOT"


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


def series_month_label(day, base):
    """The futures month the continuous front-month series was on that day."""
    if base not in CONTRACT_MONTHS:
        return ""
    by_exp, by_fnd = _front(day, base, "expiry"), _front(day, base, "fnd")
    return _label(by_exp) if by_exp == by_fnd else f"{_label(by_exp)} / {_label(by_fnd)} (rolling)"


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
    if lots and c.get("final_cif_over_lots") and cif is not None and premium:
        # A final CIF entered on a part-priced contract wins over the lots.
        mt = sum(_n(x["qty_mt"]) for x in lots)
        implied = cif / factor - premium
        out.update(type="Implied", value=implied, fixed=True, lot_mt=mt,
                   status=f"Implied from the final CIF (CIF ÷ factor − premium); pricing lots cover "
                          f"{mt:,.0f} of {qty:,.0f} MT",
                   note=f"Lots' weighted CBOT {sum(_n(x['qty_mt']) * _n(x['cbot']) for x in lots) / mt:,.2f} "
                        "shown for reference only.")
        return out
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
    """A local price stays in force until the next one is entered.

    No new local price means the market price had not changed, so the last
    one is used however old, and labelled with the date it was set. Only a
    day with no local price before it at all is left out. (``max_carry_days``
    can still impose a limit, but none is set by default.)
    """
    if age is None:
        return None, "No local price observation on or before the day"
    limit = opts.get("max_carry_days")
    if limit is not None and age > limit:
        return None, f"Local quote {age} days old — older than {limit} days"
    if age == 0:
        return "Same-day observation", ""
    if age > opts["carry_days"]:
        return f"STALE — {age} days old (last price in force)", ""
    return f"Last price in force ({age} d)", ""


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
        c["pricing_class"] = pricing_class(c)

    latest_fx = inp.get("latest_fx") or {}
    latest_cbot = {}
    for base, hist in series.items():
        if len(hist):
            spk = spikes.get(base, set())
            pairs = [(d, v) for d, v in zip(hist.dates, hist.values) if d not in spk and d <= as_of]
            if pairs:
                latest_cbot[base] = pairs[-1]
    # An open contract's cost is current, not historical: recorded CIF if fixed,
    # else latest stored CBOT + its premium; Form 4 if recorded, else the latest
    # daily FX. Its consumed tonnes and its open tonnes use the same cost.
    for c in contracts.values():
        c["current"] = current_cost(c, latest_fx, latest_cbot)
        if c.get("is_open") and c["current"]["cost_incl"] is not None:
            c["landed_egp_mt"] = c["current"]["cost_incl"]
            c["fx"], c["fx_basis"] = c["current"]["fx"], c["current"]["fx_basis"]

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
                   "base": base, "origin": "Local", "source_id": p.get("source_id", ""),
                   "cost": _n(p.get("cost_egp_mt"))}
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
        # Both transport scenarios, each side with its own inland transport:
        # imports lose only their inland freight (ocean freight stays inside
        # CIF); the local price loses the transport recorded on its quote.
        freight = _n(c.get("freight_egp_mt"))
        cost_excl = (cost - freight) if freight is not None else None
        l_trans = _n(o.get("transport"))
        l_price = _n(o.get("price"))
        if l_price is None and l_trans is not None:
            l_price = price - l_trans
        sx = (l_price - cost_excl) if None not in (l_price, cost_excl) else None
        savings_rows.append(dict(base_row, cost=cost, local=price, local_date=obs_date.isoformat(),
                                 local_age=age, local_key=loc.get("key", ""),
                                 local_source=o.get("source_id", ""), local_status=status,
                                 local_stale=age > opts["carry_days"],
                                 cif_basis=basis, saving_mt=price - cost,
                                 saving=(price - cost) * r["mt"],
                                 freight=freight, cost_excl=cost_excl, local_excl=l_price,
                                 local_transport=l_trans,
                                 local_transport_default=bool(o.get("transport_default_used")),
                                 saving_excl_mt=sx, saving_excl=(sx * r["mt"]) if sx is not None else None,
                                 storage_start=c.get("storage_start") or "",
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
        # The benchmark is the CBOT stored for the consumption day itself; the
        # contract's futures month is only the month its premium is quoted over.
        # The month the series was on that day is recorded for transparency.
        status, ok = MATCHED, True
        series_month = series_month_label(day, c["base"])
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
            "series_month": series_month,
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
        storage = _d(c.get("storage_start"))
        flags = []
        # Receipt evidence, strongest first: a logged receipt, then a recorded
        # storage start. A delivery date alone is an expectation, not a receipt.
        if c.get("receipt_logged"):
            receipt = "Confirmed — receipt logged"
        elif storage is not None:
            receipt = "Storage start recorded"
        elif dl is not None and dl > as_of:
            receipt = f"Not yet delivered (due {c.get('delivery_date')})"
        else:
            receipt = "Unverified — no storage start or receipt"
        received = c.get("receipt_logged") or storage is not None
        if dl is None and not received:
            delivered, delivery, verified = 0.0, "No delivery date — reconcile", False
        elif received:
            delivered, delivery, verified = qty, f"Delivered — {receipt.lower()}", True
        elif consumed > 1e-6:
            # Consumption estimated for a contract with no storage start or receipt:
            # kept as recorded history, flagged, never silently reclassified.
            delivered, delivery, verified = qty, "Delivery not verified — reconcile", False
            flags.append("Consumption allocated but no storage start or receipt recorded — reconcile")
        else:
            delivered, delivery, verified = 0.0, receipt, False
        if storage is not None and rows and _d(rows[0]["date"]) < storage:
            flags.append(f"FIFO consumption starts {rows[0]['date']}, before the storage start {storage.isoformat()}")
        if c.get("disc_missing"):
            flags.append("Discharge not recorded on the contract")
        if c.get("clr_missing"):
            flags.append("Clearance not recorded on the contract")
        avail = _n(stock.get(c["id"])) or 0.0
        sr = sav_by.get(c["id"], [])
        smt = _s(sr, lambda r: r["mt"])
        sv = _s(sr, lambda r: r["saving"])
        lc = _s(sr, lambda r: r["local"] * r["mt"])
        srx = [r for r in sr if r["saving_excl"] is not None]
        smx = _s(srx, lambda r: r["mt"])
        svx = _s(srx, lambda r: r["saving_excl"])
        lcx = _s(srx, lambda r: r["local_excl"] * r["mt"])
        ages = [r["local_age"] for r in sr if r["local_age"] is not None]
        cr = cb_by.get(c["id"], [])
        amt = _s([x for x in cr if x["assessable"]], lambda r: r["mt"])
        adv = _s([x for x in cr if x["assessable"]], lambda r: r["usd"])
        c.update({
            "delivered_mt": delivered, "outstanding_mt": qty - delivered, "consumed_mt": consumed,
            "available_mt": avail, "delivery_status": delivery, "delivery_verified": verified,
            "receipt_status": receipt, "received": bool(received),
            "storage_status": storage.isoformat() if storage else "Not recorded",
            "flags": flags,
            "unreconciled_mt": round(delivered - consumed - avail, 6) if delivered else round(-consumed - avail, 6),
            "first_date": rows[0]["date"] if rows else "", "last_date": rows[-1]["date"] if rows else "",
            "hist": {"priced_mt": smt, "saving": sv if sr else None,
                     "saving_mt": (sv / smt) if smt else None,
                     "local_wavg": (lc / smt) if smt else None,
                     "saving_pct": (sv / lc * 100) if lc else None,
                     "excluded_mt": consumed - smt,
                     "priced_mt_excl": smx, "saving_excl": svx if srx else None,
                     "saving_excl_mt": (svx / smx) if smx else None,
                     "local_excl_wavg": (lcx / smx) if smx else None,
                     "cost_excl": _n(c.get("landed_egp_mt")) - _n(c.get("freight_egp_mt"))
                     if None not in (_n(c.get("landed_egp_mt")), _n(c.get("freight_egp_mt"))) else None,
                     "max_local_age": max(ages) if ages else None,
                     "stale_mt": _s([r for r in sr if r["local_stale"]], lambda r: r["mt"])},
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
        for fl in flags:
            exclude("Reconciliation flag", fl, contract=c["contract"], contract_id=c["id"],
                    commodity=c["base"], mt=consumed or qty, source=c.get("source_id", ""))

    # ── open contracts and unconsumed stock vs the latest local price ────
    open_rows = []
    for c in master:
        remaining = c["available_mt"] + c["outstanding_mt"]
        if not (c.get("is_open") or c["available_mt"] > 1e-6 or (not c["received"] and remaining > 1e-6)):
            continue
        open_rows.append(open_valuation(c, remaining, latest_fx, latest_cbot, as_of, opts))

    # ── roll-ups, KPIs, data quality, validation ─────────────────────────
    hist_total = _s(savings_rows, lambda r: r["saving"])
    hist_mt = _s(savings_rows, lambda r: r["mt"])
    assessed = [r for r in cbot_rows if r["assessable"]]
    fixed_open = [r for r in open_rows if r["class"] == "Fixed price"]
    # Everything else that can be valued is indicative or provisional: unpriced
    # contracts, fixed CIF on provisional FX, contracts not yet received.
    ind_open = [r for r in open_rows if r["class"] not in ("Fixed price", "Not assessable")
                and "incomplete" not in r["class"]]
    sx_rows = [r for r in savings_rows if r["saving_excl"] is not None]
    open_c = [c for c in master if c.get("is_open")]
    k = {
        "historical_saving_egp": hist_total, "historical_mt": hist_mt,
        "historical_saving_egp_mt": (hist_total / hist_mt) if hist_mt else None,
        "historical_final_egp": _s([r for r in savings_rows if r["cif_basis"] == REALIZED], lambda r: r["saving"]),
        "historical_provisional_egp": _s([r for r in savings_rows if r["cif_basis"] == PROVISIONAL], lambda r: r["saving"]),
        "historical_saving_excl_egp": _s(sx_rows, lambda r: r["saving_excl"]),
        "historical_mt_excl": _s(sx_rows, lambda r: r["mt"]),
        "historical_saving_excl_egp_mt": (_s(sx_rows, lambda r: r["saving_excl"]) / _s(sx_rows, lambda r: r["mt"]))
        if _s(sx_rows, lambda r: r["mt"]) else None,
        "open_fixed_potential_excl_egp": _s(fixed_open, lambda r: r["potential_excl"]),
        "open_indicative_potential_excl_egp": _s(ind_open, lambda r: r["potential_excl"]),
        "open_not_received_mt": _s([r for r in open_rows if not r["received"]], lambda r: r["unconsumed_mt"]),
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
        srx = [r for r in sr if r["saving_excl"] is not None]
        mtx = _s(srx, lambda r: r["mt"])
        commodities.append({
            "saving_excl_egp": _s(srx, lambda r: r["saving_excl"]), "priced_mt_excl": mtx,
            "saving_excl_egp_mt": (_s(srx, lambda r: r["saving_excl"]) / mtx) if mtx else None,
            "cost_wavg": (_s(sr, lambda r: r["cost"] * r["mt"]) / mt) if mt else None,
            "local_wavg": (_s(sr, lambda r: r["local"] * r["mt"]) / mt) if mt else None,
            "cost_excl_wavg": (_s(srx, lambda r: r["cost_excl"] * r["mt"]) / mtx) if mtx else None,
            "local_excl_wavg": (_s(srx, lambda r: r["local_excl"] * r["mt"]) / mtx) if mtx else None,
            "open_fixed_excl_egp": _s([r for r in orr if r["class"] == "Fixed price"], lambda r: r["potential_excl"]),
            "open_indicative_excl_egp": _s([r for r in orr if r in ind_open], lambda r: r["potential_excl"]),
            "base": base, "contracts": sum(1 for c in master if c["base"] == base),
            "consumed_mt": consumed_total.get(base, 0.0),
            "allocated_import_mt": _s([a for a in alloc if a["type"] == "Import"], lambda r: r["mt"]),
            "allocated_local_mt": _s([a for a in alloc if a["type"] != "Import"], lambda r: r["mt"]),
            "excluded_mt": exc, "priced_mt": mt, "saving_egp": _s(sr, lambda r: r["saving"]),
            "saving_egp_mt": (_s(sr, lambda r: r["saving"]) / mt) if mt else None,
            "open_fixed_egp": _s([r for r in orr if r["class"] == "Fixed price"], lambda r: r["potential"]),
            "open_indicative_egp": _s([r for r in orr if r in ind_open], lambda r: r["potential"]),
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
        "stale_local": sum(1 for r in savings_rows if r["local_stale"]),
        "stale_local_mt": _s([r for r in savings_rows if r["local_stale"]], lambda r: r["mt"]),
        "stale_open": sum(1 for r in open_rows if r["local_stale"]),
        "missing_storage": sum(1 for c in master if c["storage_status"] == "Not recorded"),
        "not_received_open": sum(1 for r in open_rows if not r["received"]),
        "provisional_fx_open": sum(1 for r in open_rows if r["fx_basis"].startswith("Latest")),
        "reconciliation_flags": sum(len(c["flags"]) for c in master),
        "carried_local": sum(1 for r in savings_rows if r["local_status"].startswith("Last price")),
        "carried_local_mt": _s([r for r in savings_rows if r["local_status"].startswith("Last price")], lambda r: r["mt"]),
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
        "cbot_series": _series_window(series, spikes, master, as_of),
    }
    model["validation"] = validate(model)
    model["management_ready"] = all(v["passed"] for v in model["validation"])
    model["checksum"] = checksum(model)
    return model


def pricing_class(c):
    """Fixed / Partially fixed / Unpriced / Flat-priced, as the record supports."""
    f = c["fix"]
    if not f["eligible"]:
        return "Flat-priced" if f["type"] in ("Flat price", "") else "Not CBOT-based"
    status = (c.get("pricing_status") or "").upper()
    if status == "PRICED" or c.get("final_cif_over_lots"):
        return "Fixed"
    if status == "PARTIAL":
        return "Partially fixed"
    return "Unpriced"


def current_cost(c, latest_fx, latest_cbot):
    """CIF, FX and landed cost (with and without inland transport) as of today.

    Fixed contracts keep their recorded CIF; an unpriced CBOT contract is
    valued at the latest stored CBOT + its own premium (indicative, and a
    proxy when the stored front month is not the contract's month). FX: the
    recorded Form 4, else the contract's historical FX for a closed
    contract, else the latest daily FX (provisional).
    """
    f, base = c["fix"], c["base"]
    factor = f.get("factor")
    premium = _n(c.get("premium"))
    cif_rec = _n(c.get("cif_usd_mt"))
    pclass = c["pricing_class"]
    cbot_d, cbot_v = latest_cbot.get(base, (None, None))
    cm = c.get("contract_month")
    cbot_note = ""
    if cbot_d is not None and cm:
        series_m = series_month_label(cbot_d, base)
        cbot_note = (f"Latest stored CBOT is on {cm['code']} (front month)" if series_m == cm["code"] else
                     f"Indicative proxy: stored series is the front month ({series_m}), not the contract's "
                     f"{cm['code']} — contract-month prices are not stored")
    elif cbot_d is not None:
        cbot_note = "Indicative proxy: no futures month recorded on the contract"
    issues = []
    if pclass == "Fixed" and cif_rec is not None:
        cif, cif_basis = cif_rec, "Final CIF (fixed)"
    elif pclass in ("Unpriced", "Partially fixed") and premium and factor and cbot_v is not None:
        lots = c.get("pricing_lots") or []
        lot_mt = sum(_n(x.get("qty_mt")) or 0 for x in lots if _n(x.get("cbot")) is not None)
        qty = _n(c.get("qty_mt")) or 0.0
        if lot_mt and qty:
            lot_fix = sum((_n(x["qty_mt"]) or 0) * _n(x["cbot"]) for x in lots if _n(x.get("cbot")) is not None) / lot_mt
            share = min(lot_mt / qty, 1.0)
            cif = ((lot_fix + premium) * share + (cbot_v + premium) * (1 - share)) * factor
            cif_basis = f"Indicative CIF: lots {lot_mt:,.0f} MT fixed + rest at latest CBOT + premium"
        else:
            cif = (cbot_v + premium) * factor
            cif_basis = "Indicative CIF: (latest CBOT + premium) × factor"
    elif cif_rec is not None:
        cif, cif_basis = cif_rec, ("Provisional CIF (saved, not final)" if pclass != "Flat-priced" else "Contract CIF (flat price)")
    else:
        cif, cif_basis = None, "N/A — Missing Source Data (no CIF)"
        issues.append("no CIF")
    if not cif_basis.startswith("Indicative"):
        cbot_note = "Not used — the contract's own CIF applies"
    f4 = _n(c.get("form4_fx"))
    if f4:
        fx, fx_basis, fx_date = f4, "Form 4", c.get("form4_date") or ""
    elif not c.get("is_open") and _n(c.get("fx")):
        fx, fx_basis, fx_date = _n(c.get("fx")), f"{c.get('fx_basis') or 'Recorded FX'} (historical)", c.get("fx_date") or ""
    elif _n(latest_fx.get("rate")):
        fx, fx_basis, fx_date = _n(latest_fx["rate"]), "Latest market FX — provisional (Form 4 pending)", latest_fx.get("date", "")
    else:
        fx, fx_basis, fx_date = None, "N/A — Missing Source Data (no FX)", ""
        issues.append("no FX")
    disc, clr, freight = _n(c.get("discharge_egp_mt")) or 0.0, _n(c.get("clearance_egp_mt")) or 0.0, _n(c.get("freight_egp_mt"))
    cost_excl = (cif * fx + disc + clr) if None not in (cif, fx) else None
    cost_incl = (cost_excl + freight) if None not in (cost_excl, freight) else None
    if freight is None:
        issues.append("no inland transport on the contract")
    return {"cif": cif, "cif_basis": cif_basis, "fx": fx, "fx_basis": fx_basis, "fx_date": fx_date,
            "form4": f4, "cbot": cbot_v, "cbot_date": cbot_d.isoformat() if cbot_d else "", "cbot_note": cbot_note,
            "disc": disc, "clr": clr, "freight": freight, "cost_excl": cost_excl, "cost_incl": cost_incl,
            "issues": issues}


def open_valuation(c, remaining, latest_fx, latest_cbot, as_of, opts):
    """Current valuation of a contract's unconsumed tonnes against the latest local price."""
    f, base = c["fix"], c["base"]
    cm = c.get("contract_month")
    pclass = c["pricing_class"]
    cur = c.get("current") or current_cost(c, latest_fx, latest_cbot)
    cif, cif_basis, fx, fx_basis, fx_date = cur["cif"], cur["cif_basis"], cur["fx"], cur["fx_basis"], cur["fx_date"]
    disc, clr, freight, cost_excl, cost_incl = cur["disc"], cur["clr"], cur["freight"], cur["cost_excl"], cur["cost_incl"]
    issues = list(cur["issues"])
    f4, cbot_v, cbot_note = cur["form4"], cur["cbot"], cur["cbot_note"]
    cbot_d = _d(cur["cbot_date"])
    premium = _n(c.get("premium"))
    l_price, l_trans = _n(c.get("local_today_price")), _n(c.get("local_today_transport"))
    l_incl = _n(c.get("local_today"))
    l_date = _d(c.get("local_today_date"))
    age = (as_of - l_date).days if l_date else None
    if l_price is None and None not in (l_incl, l_trans):
        l_price = l_incl - l_trans
    if l_incl is None and None not in (l_price, l_trans):
        l_incl = l_price + l_trans
    if l_date is None:
        issues.append("no local price")
    sx = (l_price - cost_excl) if None not in (l_price, cost_excl) else None
    si = (l_incl - cost_incl) if None not in (l_incl, cost_incl) else None
    if not c["received"]:
        cls = "Current market valuation — not received"
    elif issues or (sx is None and si is None):
        cls = "Not assessable"
    elif cif_basis.startswith("Final CIF") and not fx_basis.startswith("Latest"):
        cls = "Fixed price"
    elif cif_basis.startswith("Final CIF"):
        cls = "Fixed CIF — provisional FX"
    else:
        cls = "Indicative (unpriced)"
    if c["received"] and pclass == "Flat-priced" and cls == "Indicative (unpriced)":
        cls = "Fixed price" if not fx_basis.startswith("Latest") else "Fixed CIF — provisional FX"
    if issues and cls != "Not assessable":
        cls += " · incomplete"
    return {
        "contract_id": c["id"], "contract": c["contract"], "supplier": c.get("supplier", ""),
        "commodity": c.get("commodity", ""), "origin": c.get("origin", ""), "base": base,
        "status": c.get("status", ""), "is_open": bool(c.get("is_open")), "qty_mt": c.get("qty_mt"),
        "delivered_mt": c["delivered_mt"], "consumed_mt": c["consumed_mt"], "available_mt": c["available_mt"],
        "outstanding_mt": c["outstanding_mt"], "unconsumed_mt": remaining,
        "storage_start": c.get("storage_start") or "", "storage_status": c["storage_status"],
        "receipt_status": c["receipt_status"], "received": c["received"],
        "pricing_status": c.get("pricing_status", ""), "pricing_class": pclass,
        "premium": premium, "unit": f.get("unit", ""), "futures": (cm or {}).get("code", c.get("futures_month", "")),
        "fixed_cbot": f.get("value"), "fix_type": f.get("type", ""),
        "latest_cbot": cbot_v, "latest_cbot_date": cbot_d.isoformat() if cbot_d else "", "cbot_note": cbot_note,
        "cif": cif, "cif_basis": cif_basis, "fx": fx, "fx_basis": fx_basis, "fx_date": fx_date,
        "form4_status": "Recorded" if f4 else ("Pending / Not recorded" if c.get("is_open") else "Not recorded"),
        "discharge": disc, "clearance": clr, "freight": freight,
        "disc_missing": bool(c.get("disc_missing")), "clr_missing": bool(c.get("clr_missing")),
        "notes": [n for n, m in (("discharge not recorded — cost excludes it", c.get("disc_missing")),
                                 ("clearance not recorded — cost excludes it", c.get("clr_missing"))) if m],
        "cost_excl": cost_excl, "cost_incl": cost_incl, "landed": cost_incl,
        "local_excl": l_price, "local_transport": l_trans, "local_incl": l_incl, "local": l_incl,
        "local_date": l_date.isoformat() if l_date else "", "local_age": age,
        "local_stale": age is not None and age > opts["carry_days"],
        "local_key": c.get("local_today_key", ""),
        "saving_excl_mt": sx, "saving_mt": si,
        "potential_excl": sx * remaining if sx is not None else None,
        "potential": si * remaining if si is not None else None,
        "class": cls, "issues": issues, "delivery_status": c["delivery_status"],
    }


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
                   f"{cb['avg_cbot']:,.2f} on its consumption days — {kind} of "
                   f"USD {abs(cb['usd']):,.0f} on {cb['assessed_mt']:,.0f} MT "
                   f"({(cb['coverage'] or 0) * 100:,.0f}% of its consumed tonnes); a historical benchmark, "
                   "not money that was certainly available.")
    elif f["fixed"] and cb["consumed_mt"]:
        out.append(f"CBOT fixed at {f['value']:,.2f} {f['unit']}; no consumption day fell on its own futures "
                   "month in the stored series, so the CBOT comparison is not assessable.")
    elif f["eligible"] and not f["fixed"]:
        out.append(f["status"] + (f" (indicative {f['indicative']:,.2f} {f['unit']})." if f["indicative"] else "."))
    return " ".join(out)


def _series_window(series, spikes, master, as_of):
    """The stored CBOT per commodity over the period the report covers (spikes left out)."""
    out = {}
    for base, hist in series.items():
        dates = [_d(c.get("delivery_date")) for c in master if c["base"] == base and c["fix"]["fixed"]]
        dates = [d for d in dates if d]
        if not dates or not len(hist):
            continue
        start = min(dates) - dt.timedelta(days=150)
        spk = spikes.get(base, set())
        out[base] = [[d.isoformat(), v] for d, v in zip(hist.dates, hist.values)
                     if start <= d <= as_of and d not in spk]
    return out


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
    stale = [r for r in m["cbot"] if r["assessable"] and r["cbot_date"] and
             (_d(r["date"]) - _d(r["cbot_date"])).days > m["options"]["cbot_max_age_days"]]
    check("Consumption-day CBOT from the stored daily series", not nonmatched and not stale,
          f"{sum(1 for r in m['cbot'] if r['assessable'])} day-rows compared with the CBOT stored for the day "
          f"(at most {m['options']['cbot_max_age_days']} days back over weekends/holidays; one-day spikes stepped over)"
          if not (nonmatched or stale) else f"{len(nonmatched) + len(stale)} rows outside the rule")
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
    limit = m["options"].get("max_carry_days")
    both = [r for r in m["savings"] if r["saving_excl"] is not None]
    lhs = sum(r["saving"] - r["saving_excl"] for r in both)
    rhs = sum(((r["local_transport"] or 0.0) - (r["freight"] or 0.0)) * r["mt"] for r in both)
    check("Transport scenarios reconcile", abs(lhs - rhs) < 1.0,
          f"incl − excl savings {lhs:,.0f} EGP = (local transport − import inland freight) × MT {rhs:,.0f} EGP "
          f"over {len(both)} day-rows; each side uses its own recorded transport")
    o_fixed = sum((r["potential"] or 0.0) for r in m["open"] if r["class"] == "Fixed price")
    check("Open totals reconcile to their rows", abs(o_fixed - k["open_fixed_potential_egp"]) < 0.5,
          f"confirmed {k['open_fixed_potential_egp']:,.0f} EGP incl. transport; indicative / provisional "
          f"{k['open_indicative_potential_egp']:,.0f} EGP kept separate; not-assessable rows excluded")
    unsupported = [r for r in m["savings"] if r["local_age"] is None or (limit is not None and r["local_age"] > limit)]
    check("Manager figures exclude unsupported inputs", not unsupported,
          "every local price used is a stored price in force on that day (the last one entered); days with no "
          "local price before them are listed under Excluded & Missing Data" if not unsupported else f"{len(unsupported)} rows")
    return out

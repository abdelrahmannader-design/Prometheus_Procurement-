"""Daily commodity brief: the market situation of each commodity, for a morning email.

Built from the management report model (no new calculation rules):

1. Market today      — live CBOT and FX with their change over 1 day, 1 week and 1 month.
2. Local market      — the latest local price of each commodity and its change.
3. Import vs local   — a replacement import today at the premium, port costs and route
                       freight of the latest contract of that commodity and origin, against
                       today's local price; and the premium the local price amounts to.
4. Open position     — tonnes still to consume, tonnes not priced, potential, break-even.
5. Stock cover       — stock on hand and outstanding against the configured daily rate.
6. Watch list        — triggered pricing alerts, the changes since the last report and the
                       most important data to fix.

``write_excel`` gives a small workbook (live formulas for the import parity), and
``write_pdf`` a one/two-page A4 landscape summary to attach to the email.
"""
from __future__ import annotations

import datetime as dt
import re

FACTORS = {"CORN": 0.3937, "SOYBEAN": 0.36745, "WHEAT": 0.36745, "SBM": 1.1023}
UNITS = {"CORN": "¢/bu", "SOYBEAN": "¢/bu", "WHEAT": "¢/bu", "SBM": "$/st"}


def _n(v):
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def _d(v):
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _on_or_before(series, day):
    """Last (date, value) of a date-sorted series on or before ``day``."""
    pick = None
    for d, v in series:
        if d <= day:
            pick = (d, v)
        else:
            break
    return pick


def _changes(series, now_date, now_value):
    """Change against the last value before ``now_date``, and the values on or before 7 and 30 days back."""
    prior = [x for x in series if x[0] < now_date and x[1] is not None]
    out = {}
    base = _d(now_date)
    for key, days in (("d1", None), ("d7", 7), ("d30", 30)):
        ref = (prior[-1] if prior else None) if days is None else \
            _on_or_before(prior, (base - dt.timedelta(days=days)).isoformat() if base else "")
        out[key] = (now_value - ref[1]) if (ref and now_value is not None) else None
        out[key + "_ref"] = ref[0] if ref else ""
    return out


def _decision(sav, threshold):
    return ("Missing data" if sav is None else "Strong import edge" if sav >= threshold
            else "Marginal" if sav > 0 else "Weak vs local")


def open_position(model, app_position=None, threshold=200.0):
    """Every contract not closed, as the app's Home table shows it, grouped by commodity.

    ``app_position`` are the app's own rows (same cost function as its screen); without
    them the rows come from the report model's current valuation (live CBOT, latest FX).
    """
    rem = {o["contract_id"]: o.get("unconsumed_mt") or 0.0 for o in model.get("open") or []}
    stock = {o["contract_id"]: o.get("available_mt") or 0.0 for o in model.get("open") or []}
    rows = []
    if app_position:
        rows = [dict(r) for r in app_position]
        source = "app"
    else:
        source = "report model"
        for c in sorted(model.get("contracts") or [], key=lambda c: c.get("delivery_date") or c.get("storage_start") or ""):
            if (c.get("status") or "Open") == "Closed":
                continue
            cur = c.get("current") or {}
            f = c.get("fix") or {}
            prem, cb = _n(c.get("premium")), _n(cur.get("cbot"))
            fut = (c.get("contract_month") or {}).get("code") or c.get("futures_month") or ""
            formula = (f"({cb:.2f}+{prem:.2f})×{f.get('factor')} | {fut}" if f.get("eligible") and not f.get("fixed")
                       and None not in (cb, prem) else "fixed" if f.get("fixed") else "")
            own, loc = _n(c.get("landed_egp_mt")), _n(c.get("local_today"))
            sav = (loc - own) if None not in (own, loc) else None
            qty = _n(c.get("qty_mt"))
            comm = (c.get("commodity") or c["base"]).upper()
            rows.append({"contract_id": c["id"], "contract": c.get("contract", ""), "supplier": c.get("supplier", ""),
                         "commodity": comm, "base": c["base"], "origin": c.get("origin", ""), "status": c.get("status") or "Open",
                         "qty": qty, "cif": _n(cur.get("cif")) or _n(c.get("cif_usd_mt")), "cif_formula": formula,
                         "fx": _n(cur.get("fx")) or _n(c.get("fx")), "freight": _n(c.get("freight_egp_mt")),
                         "own_after": own, "local": loc, "local_date": c.get("local_today_date") or "", "local_flag": "",
                         "sav_mt": sav, "total_sav": sav * qty if None not in (sav, qty) else None,
                         "decision": _decision(sav, threshold)})
    for r in rows:
        r["to_consume_mt"] = rem.get(r["contract_id"], 0.0)
        r["stock_mt"] = stock.get(r["contract_id"], 0.0)
        r["sav_to_consume"] = r["sav_mt"] * r["to_consume_mt"] if r.get("sav_mt") is not None else None
    groups = []
    order = ["CORN", "SOYBEAN", "SBM", "SFM", "DDGS"]
    for base in [b for b in order if any(r["base"] == b for r in rows)] + sorted({r["base"] for r in rows} - set(order)):
        g = [r for r in rows if r["base"] == base]
        qty = sum(r["qty"] or 0 for r in g)
        groups.append({"base": base, "rows": g, "contracts": len(g), "qty": qty,
                       "to_consume_mt": sum(r["to_consume_mt"] for r in g),
                       "own_after": sum((r["own_after"] or 0) * (r["qty"] or 0) for r in g) / qty if qty else None,
                       "local": sum((r["local"] or 0) * (r["qty"] or 0) for r in g) / qty if qty else None,
                       "total_sav": sum(r["total_sav"] or 0 for r in g),
                       "sav_to_consume": sum(r["sav_to_consume"] or 0 for r in g)})
    for g in groups:
        g["sav_mt"] = g["total_sav"] / g["qty"] if g["qty"] else None
    qty = sum(g["qty"] for g in groups)
    return {"source": source, "groups": groups, "qty": qty, "total_sav": sum(g["total_sav"] for g in groups),
            "to_consume_mt": sum(g["to_consume_mt"] for g in groups),
            "sav_to_consume": sum(g["sav_to_consume"] for g in groups),
            "own_after": sum((g["own_after"] or 0) * g["qty"] for g in groups) / qty if qty else None,
            "sav_mt": sum(g["total_sav"] for g in groups) / qty if qty else None}


def fifo_stock(model):
    """Stock on hand, lot by lot in FIFO order, against today's CBOT and today's local price.

    vs CBOT: (live CBOT − the lot's fixed CBOT) × factor × FX × MT — what the same tonnes would
    cost more (+) or less (−) at today's CBOT and the same premium; unpriced lots float with the CBOT.
    vs local: (local today − landed cost) × MT, including and excluding inland transport.
    Expected consumption: the configured daily rate applied in FIFO order from today.
    """
    as_of = _d(model.get("as_of")) or dt.date.today()
    rates = model.get("rates") or {}
    lots = [o for o in model.get("open") or [] if (o.get("available_mt") or 0) > 1e-6]
    cons = {c["id"]: c for c in model.get("contracts") or []}
    out = []
    for code in sorted({(cons.get(o["contract_id"], {}).get("commodity") or o["base"]) for o in lots}):
        g = sorted([o for o in lots if (cons.get(o["contract_id"], {}).get("commodity") or o["base"]) == code],
                   key=lambda o: (o.get("storage_start") or "9999", o["contract"]))
        rate = _n(rates.get(code)) or _n(rates.get(g[0]["base"]))
        cum = 0.0
        for o in g:
            mt = o["available_mt"]
            fac = FACTORS.get(o["base"])
            fixed, live = _n(o.get("fixed_cbot")), _n(o.get("latest_cbot"))
            fx = _n(o.get("fx"))
            d = (live - fixed) if None not in (fixed, live) else None
            vs_cbot = d * fac * fx * mt if None not in (d, fac, fx) else None
            start = as_of + dt.timedelta(days=cum / rate) if rate else None
            cum += mt
            end = as_of + dt.timedelta(days=cum / rate) if rate else None
            si, sx = _n(o.get("saving_mt")), _n(o.get("saving_excl_mt"))
            out.append({"code": code, "base": o["base"], "contract": o["contract"], "contract_id": o["contract_id"],
                        "supplier": o.get("supplier", ""), "storage_start": o.get("storage_start") or "not recorded",
                        "stock_mt": mt, "pricing": o.get("pricing_class", ""), "premium": _n(o.get("premium")),
                        "unit": UNITS.get(o["base"], ""), "fixed_cbot": fixed, "live_cbot": live,
                        "cbot_diff": d, "vs_cbot_egp": vs_cbot, "cif": _n(o.get("cif")), "fx": fx,
                        "cost_excl": _n(o.get("cost_excl")), "cost_incl": _n(o.get("cost_incl")),
                        "local_excl": _n(o.get("local_excl")), "local_incl": _n(o.get("local_incl")),
                        "local_date": o.get("local_date") or "",
                        "sav_incl_mt": si, "sav_excl_mt": sx,
                        "vs_local_incl": si * mt if si is not None else None, "vs_local_excl": sx * mt if sx is not None else None,
                        "use_from": start.isoformat() if start else "", "use_to": end.isoformat() if end else "",
                        "daily_rate": rate})
    tot = {}
    for r in out:
        t = tot.setdefault(r["code"], {"code": r["code"], "base": r["base"], "lots": 0, "stock_mt": 0.0, "vs_cbot_egp": 0.0,
                                       "vs_local_incl": 0.0, "vs_local_excl": 0.0, "use_to": "", "daily_rate": r["daily_rate"]})
        t["lots"] += 1
        t["stock_mt"] += r["stock_mt"]
        for k in ("vs_cbot_egp", "vs_local_incl", "vs_local_excl"):
            t[k] += r[k] or 0.0
        t["use_to"] = max(t["use_to"], r["use_to"])
    return {"lots": out, "totals": list(tot.values())}


def build(model, app_position=None, threshold=200.0):
    as_of = _d(model.get("as_of")) or dt.date.today()
    today = as_of.isoformat()
    live = model.get("live_cbot") or {}
    series = {b: [(str(d)[:10], _n(v)) for d, v in rows] for b, rows in (model.get("cbot_series") or {}).items()}

    # 1. market
    market = []
    for base in sorted(set(series) | set(live)):
        q = live.get(base) or {}
        s = series.get(base, [])
        now_v = _n(q.get("price")) if q else (s[-1][1] if s else None)
        now_t = str(q.get("time") or (s[-1][0] if s else ""))[:16]
        now_d = now_t[:10] or today
        ch = _changes(s, now_d, now_v)
        market.append({"item": f"CBOT {base}", "base": base, "unit": UNITS.get(base, ""), "value": now_v, "time": now_t,
                       "basis": "live quote" if q else "last stored close", **ch})
    fxs = [(str(d)[:10], _n(v)) for d, v in (model.get("fx_series") or [])]
    if fxs:
        market.append({"item": "FX EGP/USD", "base": "FX", "unit": "EGP", "value": fxs[-1][1], "time": fxs[-1][0],
                       "basis": "latest daily FX", **_changes(fxs, fxs[-1][0], fxs[-1][1])})

    # 2. local market
    by_key = {}
    for o in model.get("local_obs") or []:
        by_key.setdefault(o["key"], []).append(o)
    local = []
    for key in sorted(by_key):
        obs = sorted(by_key[key], key=lambda o: o["date"])
        last = obs[-1]
        sx = [(o["date"], _n(o.get("price"))) for o in obs]
        ch = _changes(sx, last["date"], _n(last.get("price")))
        local.append({"key": key, "base": last.get("base", ""), "date": last["date"], "age": (as_of - _d(last["date"])).days,
                      "price": _n(last.get("price")), "transport": _n(last.get("transport")),
                      "delivered": _n(last.get("delivered")), **ch})
    loc = {r["key"]: r for r in local}

    # 3. import vs local: replacement import at the latest contract of each commodity code
    latest_by_code = {}
    for c in model.get("contracts") or []:
        f = c.get("fix") or {}
        if not f.get("eligible") or _n(c.get("premium")) is None or c.get("base") not in FACTORS:
            continue
        when = c.get("storage_start") or c.get("delivery_date") or c.get("pricing_date") or ""
        code = c.get("commodity") or c["base"]
        if code not in latest_by_code or when > latest_by_code[code][0]:
            latest_by_code[code] = (when, c)
    fx_now = fxs[-1][1] if fxs else None
    parity = []
    for code, (when, c) in sorted(latest_by_code.items()):
        base = c["base"]
        lp = loc.get(code) or loc.get(base)
        cb = _n((live.get(base) or {}).get("price")) or (series.get(base) or [[None, None]])[-1][1]
        fac = FACTORS[base]
        prem = _n(c.get("premium"))
        disc, clr = _n(c.get("discharge_egp_mt")) or 0.0, _n(c.get("clearance_egp_mt")) or 0.0
        fr = _n(c.get("freight_egp_mt"))
        row = {"code": code, "base": base, "unit": UNITS.get(base, ""), "ref_contract": c.get("contract", ""),
               "ref_date": when, "premium": prem, "cbot": cb, "factor": fac, "fx": fx_now, "discharge": disc,
               "clearance": clr, "freight": fr, "freight_basis": c.get("freight_basis", ""),
               "local_key": lp["key"] if lp else "", "local_date": lp["date"] if lp else "",
               "local_excl": lp["price"] if lp else None, "local_transport": lp["transport"] if lp else None}
        if None not in (cb, prem, fx_now):
            row["cif"] = (cb + prem) * fac
            row["import_excl"] = row["cif"] * fx_now + disc + clr
            row["import_incl"] = row["import_excl"] + fr if fr is not None else None
        if row.get("import_excl") is not None and row["local_excl"] is not None:
            row["edge_excl"] = row["local_excl"] - row["import_excl"]
            row["eq_premium"] = (row["local_excl"] - disc - clr) / fx_now / fac - cb
            row["premium_gap"] = row["eq_premium"] - prem
            row["be_cbot"] = (row["local_excl"] - disc - clr) / fx_now / fac - prem
        if row.get("import_incl") is not None and row["local_excl"] is not None and row["local_transport"] is not None:
            row["edge_incl"] = row["local_excl"] + row["local_transport"] - row["import_incl"]
        row["ref_note"] = "; ".join(x for x in (
            "clearance not recorded on the reference contract (0 used)" if c.get("clr_missing") else "",
            "discharge not recorded on the reference contract (0 used)" if c.get("disc_missing") else "",
            "no route freight on the reference contract — add manually" if fr is None else "") if x)
        row["verdict"] = ("Import cheaper" if (row.get("edge_incl") if row.get("edge_incl") is not None else row.get("edge_excl") or 0) > 0
                          else "Local cheaper" if row.get("edge_excl") is not None else "Not assessable")
        parity.append(row)

    # 4. open position by commodity
    pos = {}
    for o in model.get("open") or []:
        if (o.get("unconsumed_mt") or 0) <= 1e-6:
            continue
        p = pos.setdefault(o["base"], {"base": o["base"], "contracts": 0, "remaining_mt": 0.0, "stock_mt": 0.0,
                                       "outstanding_mt": 0.0, "unpriced_mt": 0.0, "pot_incl": 0.0, "pot_excl": 0.0,
                                       "head_w": 0.0, "head_mt": 0.0, "min_head": None, "min_head_contract": ""})
        p["contracts"] += 1
        p["remaining_mt"] += o["unconsumed_mt"]
        p["stock_mt"] += o.get("available_mt") or 0.0
        p["outstanding_mt"] += o.get("outstanding_mt") or 0.0
        if o.get("pricing_class") in ("Unpriced", "Partially fixed"):
            p["unpriced_mt"] += o["unconsumed_mt"]
        p["pot_incl"] += o.get("potential") or 0.0
        p["pot_excl"] += o.get("potential_excl") or 0.0
        h = o.get("headroom_incl") if o.get("headroom_incl") is not None else o.get("headroom_excl")
        if h is not None and o.get("pricing_class") in ("Unpriced", "Partially fixed"):
            p["head_w"] += h * o["unconsumed_mt"]
            p["head_mt"] += o["unconsumed_mt"]
            if p["min_head"] is None or h < p["min_head"]:
                p["min_head"], p["min_head_contract"] = h, o["contract"]
    position = []
    for p in sorted(pos.values(), key=lambda x: x["base"]):
        p["avg_headroom"] = p["head_w"] / p["head_mt"] if p["head_mt"] else None
        position.append({k: v for k, v in p.items() if k not in ("head_w", "head_mt")})

    # 5. stock cover against the configured daily rates
    rates = model.get("rates") or {}
    rate_by_base = {}
    for code, r in rates.items():
        base = code.split("-")[0] if code.split("-")[0] in FACTORS or code.split("-")[0] in ("DDGS", "SFM") else code
        rate_by_base[base] = rate_by_base.get(base, 0.0) + (_n(r) or 0.0)
    stock_by = {}
    for o in model.get("open") or []:
        s = stock_by.setdefault(o["base"], [0.0, 0.0])
        s[0] += o.get("available_mt") or 0.0
        s[1] += o.get("outstanding_mt") or 0.0
    cons = {}
    for a in model.get("allocations") or []:
        d = _d(a["date"])
        if d and d <= as_of and (as_of - d).days < 7:
            cons[a["base"]] = cons.get(a["base"], 0.0) + (a.get("mt") or 0.0)
    cover = []
    for base in sorted(set(rate_by_base) | set(stock_by)):
        st, out = stock_by.get(base, [0.0, 0.0])
        rate = rate_by_base.get(base)
        cover.append({"base": base, "stock_mt": st, "outstanding_mt": out, "daily_rate": rate,
                      "consumed_7d": cons.get(base, 0.0),
                      "cover_days": st / rate if rate else None, "cover_days_incl_outstanding": (st + out) / rate if rate else None})

    trig = [a for a in model.get("alerts") or [] if a.get("status") == "TRIGGERED"]
    fixes = [r for r in model.get("data_to_fix") or [] if r["severity"] in ("High", "Medium")]
    since = model.get("since_last") or {"previous": None, "rows": []}
    exp = model.get("exposure") or {}
    k = model.get("kpis") or {}
    headline = []
    for r in parity:
        if r.get("edge_excl") is not None:
            e = r["edge_incl"] if r.get("edge_incl") is not None else r["edge_excl"]
            headline.append(f"{r['code']}: {'import' if e > 0 else 'local'} cheaper by {abs(e):,.0f} EGP/MT "
                            f"({'incl.' if r.get('edge_incl') is not None else 'excl.'} transport)")
    threshold = (app_position[0].get("threshold") if app_position else None) or threshold
    return {"as_of": today, "generated": model.get("generated", ""), "market": market, "local": local, "parity": parity,
            "open_position": open_position(model, app_position, threshold), "fifo": fifo_stock(model),
            "position": position, "cover": cover, "alerts": trig, "alerts_all": model.get("alerts") or [],
            "fixes": fixes, "fixes_total": len(model.get("data_to_fix") or []), "since_last": since, "exposure": exp,
            "headline": headline,
            "kpis": {"historical_saving_egp": k.get("historical_saving_egp"),
                     "open_fixed_potential_egp": k.get("open_fixed_potential_egp"),
                     "open_indicative_potential_egp": k.get("open_indicative_potential_egp"),
                     "cbot_net_usd": k.get("cbot_net_usd")},
            "checksum": model.get("checksum", "")}


# ── Excel ────────────────────────────────────────────────────────────────

def write_excel(brief, path):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    navy, light = PatternFill("solid", fgColor="1F2A44"), PatternFill("solid", fgColor="EEF2F8")
    hfont, bold = Font(color="FFFFFF", bold=True), Font(bold=True)
    red, green = Font(color="B00020"), Font(color="1B7F3B")
    wb = Workbook()

    def sheet(title, note, heads, rows, widths, fmt=None, first=False):
        ws = wb.active if first else wb.create_sheet()
        ws.title = title
        ws["A1"] = f"{title} — {brief['as_of']}"
        ws["A1"].font = Font(bold=True, size=13)
        ws["A2"] = note
        ws["A2"].alignment = Alignment(wrap_text=True, vertical="top")
        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=max(len(heads), 1))
        ws.row_dimensions[2].height = 32
        for j, h in enumerate(heads, 1):
            c = ws.cell(row=4, column=j, value=h)
            c.fill, c.font = navy, hfont
            c.alignment = Alignment(wrap_text=True, vertical="center")
        ws.row_dimensions[4].height = 30
        for i, r in enumerate(rows, 5):
            for j, v in enumerate(r, 1):
                c = ws.cell(row=i, column=j, value=v)
                if fmt and j in fmt:
                    c.number_format = fmt[j]
                if i % 2 == 0:
                    c.fill = light
        for j, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(j)].width = w
        ws.freeze_panes = "B5"
        return ws

    # Brief (summary)
    lines = [["Headline"]] + [[h] for h in brief["headline"]] + [[""]]
    lines += [["Pricing alerts triggered", len(brief["alerts"])]] + [[f"  {a['contract']}: {'; '.join(a['triggered'])}"] for a in brief["alerts"]]
    lines += [["Data to fix (high / medium)", len(brief["fixes"])]]
    k = brief["kpis"]
    lines += [[""], ["Historical savings incl. transport (EGP)", k["historical_saving_egp"]],
              ["Open potential — confirmed (EGP)", k["open_fixed_potential_egp"]],
              ["Open potential — indicative (EGP)", k["open_indicative_potential_egp"]],
              ["CBOT benchmark net (USD)", k["cbot_net_usd"]]]
    exp = brief["exposure"] or {}
    if exp:
        lines += [[""], ["Tonnes not priced", exp.get("total_unpriced_mt")],
                  ["EGP effect of a 10 ¢ CBOT move on them", exp.get("total_cbot_egp_per_step")],
                  ["Tonnes on provisional FX (no Form 4)", exp.get("total_fx_mt")],
                  ["EGP effect of a 1 EGP FX move on them", exp.get("total_fx_egp_per_step")]]
    ws = sheet("Brief", "One-page summary. Each sheet has the detail; figures come from the management report "
               f"(checksum {brief['checksum']}).", ["Item", "Value"], lines, [70, 18], {2: "#,##0"}, first=True)

    sheet("Market", "Live CBOT (the quote the app values open contracts at) and FX, with the change since the "
          "previous close, a week and a month ago.",
          ["Item", "Unit", "Value", "Time", "Basis", "Δ vs previous", "Previous date", "Δ 1 week", "Δ 1 month"],
          [[m["item"], m["unit"], m["value"], m["time"], m["basis"], m["d1"], m["d1_ref"], m["d7"], m["d30"]] for m in brief["market"]],
          [18, 8, 11, 17, 16, 13, 13, 11, 11], {3: "#,##0.00##", 6: "+#,##0.00;-#,##0.00", 8: "+#,##0.00;-#,##0.00", 9: "+#,##0.00;-#,##0.00"})

    sheet("Local Market", "Latest local price of each commodity (EGP/MT, without transport) and its change.",
          ["Commodity", "Date", "Age (days)", "Price excl. transport", "Transport", "Delivered", "Δ vs previous quote", "Previous quote date",
           "Δ 1 week", "Δ 1 month"],
          [[r["key"], r["date"], r["age"], r["price"], r["transport"], r["delivered"], r["d1"], r["d1_ref"], r["d7"], r["d30"]] for r in brief["local"]],
          [14, 12, 10, 14, 11, 12, 14, 14, 11, 11], {4: "#,##0", 5: "#,##0.00", 6: "#,##0", 7: "+#,##0;-#,##0", 9: "+#,##0;-#,##0", 10: "+#,##0;-#,##0"})

    heads = ["Commodity", "Reference contract", "Its date", "Premium", "Unit", "CBOT now", "Factor", "FX", "CIF $/MT",
             "Discharge", "Clearance", "Import excl. transport", "Inland freight", "Import incl. transport",
             "Local excl.", "Local transport", "Local date", "Edge excl. (local − import)", "Edge incl.",
             "Local equiv. premium", "Premium gap", "Break-even CBOT (excl.)", "Verdict", "Freight basis", "Note"]
    ws = sheet("Import vs Local", "A replacement import bought today at the premium, port costs and route freight of the "
               "latest contract of each commodity, against today's local price. Positive edge = import cheaper. "
               "Columns I, L, N, R, S, T, U, V are live formulas.", heads, [], [12, 20, 11, 9, 7, 9, 8, 9, 9, 9, 9, 13, 10, 13,
                                                                              11, 10, 11, 13, 11, 12, 10, 13, 14, 50])
    cache = {}
    for i, r in enumerate(brief["parity"], 5):
        # Results stored with each formula, so a mail preview (which does not recalculate) shows the numbers.
        e = lambda k: "" if r.get(k) is None else r[k]
        cache.update({f"I{i}": e("cif"), f"L{i}": e("import_excl"), f"N{i}": e("import_incl"), f"R{i}": e("edge_excl"),
                      f"S{i}": e("edge_incl"), f"T{i}": e("eq_premium"), f"U{i}": e("premium_gap"), f"V{i}": e("be_cbot")})
        vals = [r["code"], r["ref_contract"], r["ref_date"], r["premium"], r["unit"], r["cbot"], r["factor"], r["fx"]]
        for j, v in enumerate(vals, 1):
            ws.cell(row=i, column=j, value=v)
        ws.cell(row=i, column=9, value=f"=IF(AND(ISNUMBER(F{i}),ISNUMBER(D{i})),(F{i}+D{i})*G{i},\"\")")
        ws.cell(row=i, column=10, value=r["discharge"]); ws.cell(row=i, column=11, value=r["clearance"])
        ws.cell(row=i, column=12, value=f"=IF(AND(ISNUMBER(I{i}),ISNUMBER(H{i})),I{i}*H{i}+J{i}+K{i},\"\")")
        ws.cell(row=i, column=13, value=r["freight"] if r["freight"] is not None else "add manually")
        ws.cell(row=i, column=14, value=f"=IF(AND(ISNUMBER(L{i}),ISNUMBER(M{i})),L{i}+M{i},\"\")")
        ws.cell(row=i, column=15, value=r["local_excl"]); ws.cell(row=i, column=16, value=r["local_transport"])
        ws.cell(row=i, column=17, value=r["local_date"])
        ws.cell(row=i, column=18, value=f"=IF(AND(ISNUMBER(O{i}),ISNUMBER(L{i})),O{i}-L{i},\"\")")
        ws.cell(row=i, column=19, value=f"=IF(AND(ISNUMBER(O{i}),ISNUMBER(P{i}),ISNUMBER(N{i})),O{i}+P{i}-N{i},\"\")")
        ws.cell(row=i, column=20, value=f"=IF(AND(ISNUMBER(O{i}),ISNUMBER(H{i}),ISNUMBER(F{i})),(O{i}-J{i}-K{i})/H{i}/G{i}-F{i},\"\")")
        ws.cell(row=i, column=21, value=f"=IF(ISNUMBER(T{i}),T{i}-D{i},\"\")")
        ws.cell(row=i, column=22, value=f"=IF(AND(ISNUMBER(O{i}),ISNUMBER(H{i})),(O{i}-J{i}-K{i})/H{i}/G{i}-D{i},\"\")")
        ws.cell(row=i, column=23, value=r["verdict"]); ws.cell(row=i, column=24, value=r["freight_basis"])
        ws.cell(row=i, column=25, value=r.get("ref_note", "")).font = red
        for j, f_ in ((4, "#,##0.00"), (6, "#,##0.00"), (7, "0.0000"), (8, "0.0000"), (9, "#,##0.00"), (10, "#,##0.00"),
                      (11, "#,##0.00"), (12, "#,##0"), (13, "#,##0.00"), (14, "#,##0"), (15, "#,##0"), (16, "#,##0.00"),
                      (18, "+#,##0;-#,##0"), (19, "+#,##0;-#,##0"), (20, "#,##0.00"), (21, "+#,##0.00;-#,##0.00"), (22, "#,##0.00")):
            ws.cell(row=i, column=j).number_format = f_
        ws.cell(row=i, column=23).font = green if r["verdict"] == "Import cheaper" else red if r["verdict"] == "Local cheaper" else Font()

    sheet("Open Position", "Tonnes still to consume per commodity, how much is not priced, the potential against today's "
          "local price, and the headroom before local becomes cheaper (unpriced tonnes).",
          ["Commodity", "Contracts", "Still to consume MT", "In stock MT", "Outstanding MT", "Not priced MT",
           "Potential incl. transport EGP", "Potential excl. transport EGP", "Avg headroom", "Tightest headroom", "Tightest contract"],
          [[p["base"], p["contracts"], p["remaining_mt"], p["stock_mt"], p["outstanding_mt"], p["unpriced_mt"], p["pot_incl"], p["pot_excl"],
            p["avg_headroom"], p["min_head"], p["min_head_contract"]] for p in brief["position"]],
          [12, 10, 14, 12, 13, 13, 17, 17, 12, 13, 22], {3: "#,##0", 4: "#,##0", 5: "#,##0", 6: "#,##0", 7: "#,##0", 8: "#,##0", 9: "#,##0.00", 10: "#,##0.00"})

    exp = brief["exposure"] or {}
    rows = [[r["base"], r["futures"], r["contracts"], r["unpriced_mt"], r["avg_premium"], r["cbot"], r["step"], r["egp_per_step"], r["contract_names"]]
            for r in exp.get("cbot", [])]
    rows += [[""], ["FX not fixed (no Form 4)"]] + [[r["base"], "", r["contracts"], r["mt"], "", "", 1, r["egp_per_step"], ""] for r in exp.get("fx", [])]
    sheet("Exposure", "Price not fixed yet: EGP cost change for a CBOT move of the step shown (10 ¢/bu; 10 $/st for SBM) "
          "and for a 1 EGP move in the FX on contracts without Form 4. Higher CBOT / FX = higher cost.",
          ["Commodity", "Futures month", "Contracts", "MT", "Avg premium", "CBOT now", "Step", "EGP per step", "Contracts"],
          rows, [12, 12, 10, 11, 11, 10, 7, 15, 70], {4: "#,##0", 5: "#,##0.00", 6: "#,##0.00", 8: "#,##0"})

    op = brief["open_position"]
    rows = []
    for g in op["groups"]:
        rows.append([f"{g['base']} ({g['contracts']} contracts)", "", "", "", "", g["qty"], g["to_consume_mt"], "", "", "", "", "",
                     g["own_after"], g["local"], g["sav_mt"], g["total_sav"], g["sav_to_consume"], ""])
        rows += [[r["contract"], r["supplier"], r["commodity"], r["origin"], r["status"], r["qty"], r["to_consume_mt"], r["stock_mt"],
                  r["cif"], r["cif_formula"], r["fx"], r["freight"], r["own_after"],
                  (r["local"] if not r.get("local_flag") else f"{r['local']:,.0f} {r['local_flag']}") if r["local"] is not None else None,
                  r["sav_mt"], r["total_sav"], r["sav_to_consume"], r["decision"]] for r in g["rows"]]
    rows.append([f"TOTAL ({sum(g['contracts'] for g in op['groups'])} open)", "", "", "", "", op["qty"], op["to_consume_mt"], "", "", "",
                 "", "", op["own_after"], "", op["sav_mt"], op["total_sav"], op["sav_to_consume"], ""])
    ws = sheet("Open Contracts", "Every contract not closed, as on the app's Home screen (" + op["source"] + "): CIF at the live "
               "CBOT + premium for unpriced contracts, today's FX unless Form 4, route freight, own cost after all fees "
               "against today's local price. Sav total = Sav/MT × contract MT (as the app); the next column uses only the "
               "tonnes still to consume. * local price older than 14 days · † today's local used as a stand-in.",
               ["Contract", "Supplier", "Commodity", "Origin", "Status", "MT", "Still to consume MT", "In stock MT", "CIF $",
                "CIF formula / live CBOT", "FX", "Freight", "Own after", "Local", "Sav/MT", "Sav total EGP (contract MT)",
                "Sav on tonnes to consume EGP", "Decision"], rows,
               [22, 15, 11, 10, 8, 9, 11, 9, 9, 30, 9, 8, 10, 10, 9, 15, 15, 18],
               {6: "#,##0", 7: "#,##0", 8: "#,##0", 9: "#,##0.00", 11: "0.0000", 12: "#,##0", 13: "#,##0", 14: "#,##0",
                15: "+#,##0;-#,##0", 16: "+#,##0;-#,##0", 17: "+#,##0;-#,##0"})
    for i, r in enumerate(rows, 5):
        if r[0].startswith("TOTAL") or "contracts)" in r[0]:
            for j in range(1, 19):
                ws.cell(row=i, column=j).font = bold
        if r[17] in ("Strong import edge", "Weak vs local"):
            ws.cell(row=i, column=18).font = green if r[17] == "Strong import edge" else red
    fs = brief["fifo"]
    rows = [[r["code"], r["contract"], r["storage_start"], r["stock_mt"], r["use_from"], r["use_to"], r["pricing"], r["premium"],
             r["fixed_cbot"], r["live_cbot"], r["cbot_diff"], r["vs_cbot_egp"], r["cif"], r["fx"], r["cost_excl"], r["cost_incl"],
             r["local_excl"], r["local_incl"], r["sav_excl_mt"], r["sav_incl_mt"], r["vs_local_excl"], r["vs_local_incl"]] for r in fs["lots"]]
    rows += [[""]] + [[f"Total {t['code']}", f"{t['lots']} lots", "", t["stock_mt"], "", t["use_to"], "", None, None, None, None,
                       t["vs_cbot_egp"], None, None, None, None, None, None, None, None, t["vs_local_excl"], t["vs_local_incl"]]
                      for t in fs["totals"]]
    sheet("FIFO Stock", "Stock on hand lot by lot in FIFO order (oldest first), with the dates it is expected to be used at the "
          "configured daily rate. vs CBOT = (live CBOT − fixed CBOT) × factor × FX × MT: positive = the stock was fixed below "
          "today's CBOT (cheaper than buying the same now); unpriced lots float with the CBOT. vs local = (local today − landed "
          "cost) × MT.",
          ["Commodity", "Contract", "Storage date", "In stock MT", "Use from", "Use until", "Pricing", "Premium", "CBOT fixed",
           "Live CBOT", "Live − fixed", "vs CBOT EGP", "CIF $/MT", "FX", "Cost excl. transport", "Cost incl. transport",
           "Local excl.", "Local incl.", "Saving/MT excl.", "Saving/MT incl.", "vs local excl. EGP", "vs local incl. EGP"], rows,
          [11, 22, 12, 10, 11, 11, 12, 9, 10, 10, 10, 13, 9, 9, 12, 12, 11, 11, 11, 11, 14, 14],
          {4: "#,##0", 8: "#,##0.00", 9: "#,##0.00", 10: "#,##0.00", 11: "+#,##0.00;-#,##0.00", 12: "+#,##0;-#,##0",
           13: "#,##0.00", 14: "0.0000", 15: "#,##0", 16: "#,##0", 17: "#,##0", 18: "#,##0", 19: "+#,##0;-#,##0",
           20: "+#,##0;-#,##0", 21: "+#,##0;-#,##0", 22: "+#,##0;-#,##0"})

    sheet("Stock Cover", "Stock on open contracts and outstanding tonnes against the configured daily consumption rate "
          "(consumption days are FIFO estimates).",
          ["Commodity", "In stock MT", "Outstanding MT", "Daily rate MT", "Consumed last 7 days MT", "Days of cover (stock)",
           "Days of cover (stock + outstanding)"],
          [[c["base"], c["stock_mt"], c["outstanding_mt"], c["daily_rate"], c["consumed_7d"], c["cover_days"], c["cover_days_incl_outstanding"]]
           for c in brief["cover"]], [12, 12, 14, 12, 16, 16, 20], {2: "#,##0", 3: "#,##0", 4: "#,##0", 5: "#,##0", 6: "0.0", 7: "0.0"})

    rows = [["ALERT", a["contract"], a["base"], "; ".join(a["triggered"]), a.get("note", "")] for a in brief["alerts"]]
    rows += [[f["severity"], f["contract"] or "—", f["base"], f"{f['category']}: {f['detail']}", f["action"]] for f in brief["fixes"]]
    sl = brief["since_last"] or {}
    if sl.get("previous"):
        rows += [[""], [f"Since the report of {sl['previous'].get('generated')}"]]
        rows += [["Change", r["label"], r["unit"], r["now"], r["change"]] for r in sl["rows"] if r.get("change")]
    sheet("Watch List", "Triggered pricing alerts, then the data to fix (high and medium), then the changes since the last report.",
          ["Type", "Contract / item", "Commodity", "Detail", "Action / value"], rows, [10, 26, 11, 80, 50])
    order = ["Brief", "Open Contracts", "FIFO Stock", "Market", "Local Market", "Import vs Local", "Open Position",
             "Exposure", "Stock Cover", "Watch List"]
    wb._sheets.sort(key=lambda w: order.index(w.title) if w.title in order else len(order))
    wb.active = 0
    wb.calculation.fullCalcOnLoad = True
    wb.save(path)
    from .xlsx_cache import store_formula_results
    store_formula_results(path, {"Import vs Local": cache})
    return path


# ── PDF ──────────────────────────────────────────────────────────────────

def write_pdf(brief, path):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontSize=16, spaceAfter=2, alignment=0)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=11, spaceBefore=8, spaceAfter=3, textColor=colors.HexColor("#1F2A44"))
    small = ParagraphStyle("s", parent=ss["Normal"], fontSize=7.5, leading=9.5, textColor=colors.HexColor("#555555"))
    body = ParagraphStyle("b", parent=ss["Normal"], fontSize=8.5, leading=11)
    navy, light = colors.HexColor("#1F2A44"), colors.HexColor("#EEF2F8")
    GREEN, RED = colors.HexColor("#1B7F3B"), colors.HexColor("#B00020")

    def f(v, d=0, sign=False):
        if v is None or v == "":
            return "—"
        if isinstance(v, str):
            return v
        s = f"{v:+,.{d}f}" if sign else f"{v:,.{d}f}"
        return s

    def table(heads, rows, widths, colour_cols=()):
        data = [[Paragraph(f"<b>{h}</b>", ParagraphStyle("th", parent=body, fontSize=7.5, leading=9, textColor=colors.white)) for h in heads]]
        data += [[Paragraph(str(c), ParagraphStyle("td", parent=body, fontSize=7.5, leading=9)) if isinstance(c, str) and len(c) > 15 else c
                  for c in r] for r in rows]
        t = Table(data, colWidths=[w * cm for w in widths], repeatRows=1)
        st = [("BACKGROUND", (0, 0), (-1, 0), navy), ("FONTSIZE", (0, 1), (-1, -1), 7.5),
              ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, light]), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C9D1E0")),
              ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
        num = re.compile(r"^[+\-±]?[\d,]+(\.\d+)?( ?(d|EGP))?$|^—$")
        for i, r in enumerate(rows, 1):
            for j, v in enumerate(r):
                if j and (isinstance(v, (int, float)) or (isinstance(v, str) and num.match(v.strip()))):
                    st.append(("ALIGN", (j, i), (j, i), "RIGHT"))
        for col in colour_cols:
            for i, r in enumerate(rows, 1):
                v = str(r[col])
                if v.startswith("+") or v.startswith("Import"):
                    st.append(("TEXTCOLOR", (col, i), (col, i), GREEN))
                elif v.startswith("-") or v.startswith("Local"):
                    st.append(("TEXTCOLOR", (col, i), (col, i), RED))
        t.setStyle(TableStyle(st))
        return t

    doc = SimpleDocTemplate(path, pagesize=landscape(A4), leftMargin=1.2 * cm, rightMargin=1.2 * cm,
                            topMargin=1.0 * cm, bottomMargin=1.0 * cm, title=f"Daily Commodity Brief {brief['as_of']}")
    el = [Paragraph(f"Daily Commodity Brief — {brief['as_of']}", h1),
          Paragraph(f"Generated {brief['generated']} from the Prometheus management report (checksum {brief['checksum']}). "
                    "Import figures are a replacement purchase today at the latest contract's premium; "
                    "consumption days are FIFO estimates.", small)]
    if brief["headline"] or brief["alerts"]:
        items = brief["headline"] + [f"<font color='#B00020'><b>ALERT</b></font> {a['contract']}: {'; '.join(a['triggered'])}" for a in brief["alerts"]]
        el += [Spacer(1, 4)] + [Paragraph("• " + x, body) for x in items]

    el += [Paragraph("Market today", h2),
           table(["Item", "Value", "Unit", "Time", "Chg. previous", "Chg. 1 week", "Chg. 1 month", "Basis"],
                 [[m["item"], f(m["value"], 2 if m["base"] != "FX" else 4), m["unit"], m["time"], f(m["d1"], 2, True),
                   f(m["d7"], 2, True), f(m["d30"], 2, True), m["basis"]] for m in brief["market"]],
                 [3.6, 2.4, 1.6, 3.4, 2.4, 2.4, 2.4, 3.4], colour_cols=())]
    el += [Paragraph("Local market (EGP/MT, without transport)", h2),
           table(["Commodity", "Price", "Date", "Age", "Transport", "Chg. previous", "Chg. 1 week", "Chg. 1 month"],
                 [[r["key"], f(r["price"]), r["date"], f"{r['age']} d", f(r["transport"], 2), f(r["d1"], 0, True), f(r["d7"], 0, True),
                   f(r["d30"], 0, True)] for r in brief["local"]],
                 [3.2, 2.4, 2.6, 1.6, 2.2, 2.4, 2.4, 2.4])]
    el += [Paragraph("Import today vs local (EGP/MT)", h2),
           table(["Commodity", "Ref. contract", "Premium", "CBOT", "FX", "Import excl.", "Freight", "Import incl.", "Local excl.",
                  "Edge excl.", "Edge incl.", "Local eq. premium", "Gap", "Break-even CBOT", "Verdict"],
                 [[r["code"], r["ref_contract"], f(r["premium"], 2), f(r["cbot"], 2), f(r["fx"], 3), f(r.get("import_excl")),
                   f(r["freight"]), f(r.get("import_incl")), f(r["local_excl"]), f(r.get("edge_excl"), 0, True),
                   f(r.get("edge_incl"), 0, True), f(r.get("eq_premium"), 1), f(r.get("premium_gap"), 1, True),
                   f(r.get("be_cbot"), 1), r["verdict"]] for r in brief["parity"]],
                 [2.1, 3.0, 1.5, 1.5, 1.5, 1.9, 1.4, 1.9, 1.8, 1.7, 1.7, 1.9, 1.4, 1.9, 2.2], colour_cols=(9, 10, 14))]
    notes = [f"{r['code']}: {r['ref_note']}" for r in brief["parity"] if r.get("ref_note")]
    if notes:
        el += [Paragraph("Check: " + " · ".join(notes), ParagraphStyle("w", parent=small, textColor=RED))]
    op = brief["open_position"]
    if op["groups"]:
        rows, bold_rows = [], []
        for g in op["groups"]:
            bold_rows.append(len(rows) + 1)
            rows.append([f"{g['base']} ({g['contracts']})", "", "", f(g["qty"]), f(g["to_consume_mt"]), "", "", "", "",
                         f(g["own_after"]), f(g["local"]), f(g["sav_mt"], 0, True), f(g["total_sav"], 0, True), f(g["sav_to_consume"], 0, True), ""])
            rows += [[r["contract"], r["supplier"], r["origin"], f(r["qty"]), f(r["to_consume_mt"]), f(r["cif"], 2), r["cif_formula"] or "—",
                      f(r["fx"], 4), f(r["freight"]), f(r["own_after"]), (f(r["local"]) + (" " + r["local_flag"] if r.get("local_flag") else "")),
                      f(r["sav_mt"], 0, True), f(r["total_sav"], 0, True), f(r["sav_to_consume"], 0, True), r["decision"]] for r in g["rows"]]
        bold_rows.append(len(rows) + 1)
        rows.append([f"TOTAL ({sum(g['contracts'] for g in op['groups'])} open)", "", "", f(op["qty"]), f(op["to_consume_mt"]), "", "", "", "",
                     f(op["own_after"]), "", f(op["sav_mt"], 0, True), f(op["total_sav"], 0, True), f(op["sav_to_consume"], 0, True), ""])
        t = table(["Contract", "Supplier", "Origin", "MT", "To consume", "CIF $", "CIF formula / live CBOT", "FX", "Freight", "Own after",
                   "Local", "Sav/MT", "Sav total EGP", "Sav to consume", "Decision"], rows,
                  [2.8, 2.0, 1.5, 1.3, 1.4, 1.3, 3.8, 1.4, 1.1, 1.4, 1.4, 1.3, 1.9, 1.9, 2.6], colour_cols=(11, 12, 13))
        t.setStyle(TableStyle([("FONTNAME", (0, i), (-1, i), "Helvetica-Bold") for i in bold_rows] +
                              [("BACKGROUND", (0, i), (-1, i), colors.HexColor("#DCE3EF")) for i in bold_rows]))
        el += [Paragraph("Open contracts position (as on the app's Home screen)", h2), t,
               Paragraph("Sav total = Sav/MT × contract MT, as in the app; “Sav to consume” uses only the tonnes not yet consumed. "
                         "* local price older than 14 days · † today's local price used as a stand-in.", small)]
    fs = brief["fifo"]
    if fs["lots"]:
        rows = [[r["code"], r["contract"], r["storage_start"], f(r["stock_mt"]), f"{r['use_from']} → {r['use_to']}" if r["use_to"] else "—",
                 r["pricing"], f(r["fixed_cbot"], 2) if r["fixed_cbot"] is not None else "floats", f(r["live_cbot"], 2),
                 f(r["cbot_diff"], 2, True), f(r["vs_cbot_egp"], 0, True), f(r["cost_incl"]), f(r["local_incl"]),
                 f(r["sav_incl_mt"], 0, True), f(r["vs_local_incl"], 0, True), f(r["vs_local_excl"], 0, True)] for r in fs["lots"]]
        rows += [["Total", f"{t_['code']} · {t_['lots']} lot{'s' if t_['lots'] != 1 else ''}", "", f(t_["stock_mt"]), f"until {t_['use_to']}" if t_["use_to"] else "", "", "", "",
                  "", f(t_["vs_cbot_egp"], 0, True), "", "", "", f(t_["vs_local_incl"], 0, True), f(t_["vs_local_excl"], 0, True)] for t_ in fs["totals"]]
        el += [Paragraph("FIFO stock on hand vs CBOT and local", h2),
               table(["Commodity", "Contract", "Storage", "Stock MT", "Expected use (FIFO)", "Pricing", "CBOT fixed", "Live CBOT",
                      "Live − fixed", "vs CBOT EGP", "Cost incl.", "Local incl.", "Sav/MT incl.", "vs local incl. EGP", "vs local excl. EGP"],
                     rows, [1.7, 2.8, 1.7, 1.3, 3.0, 1.6, 1.4, 1.4, 1.4, 1.9, 1.4, 1.4, 1.4, 2.0, 2.0], colour_cols=(8, 9, 12, 13, 14)),
               Paragraph("vs CBOT: positive = the stock was fixed below today's CBOT (it would cost this much more to buy the same "
                         "tonnes today at the same premium); unpriced lots float with the CBOT. vs local: (today's local − landed "
                         "cost) × stock. Expected use applies the configured daily rate in FIFO order from today.", small)]
    el += [Paragraph("Open position", h2),
           table(["Commodity", "Contracts", "To consume MT", "In stock", "Outstanding", "Not priced MT", "Potential incl. EGP",
                  "Potential excl. EGP", "Avg headroom", "Tightest headroom"],
                 [[p["base"], p["contracts"], f(p["remaining_mt"]), f(p["stock_mt"]), f(p["outstanding_mt"]), f(p["unpriced_mt"]),
                   f(p["pot_incl"], 0, True), f(p["pot_excl"], 0, True), f(p["avg_headroom"], 1),
                   (f(p["min_head"], 1) + (f" ({p['min_head_contract']})" if p["min_head_contract"] else ""))] for p in brief["position"]],
                 [2.2, 1.6, 2.2, 2.0, 2.0, 2.2, 2.8, 2.8, 2.0, 5.0], colour_cols=(6, 7))]
    exp = brief["exposure"] or {}
    if exp.get("cbot") or exp.get("fx"):
        rows = [[r["base"], r["futures"], f(r["unpriced_mt"]), f(r["cbot"], 2), f"±{r['step']:g}", f(r["egp_per_step"])] for r in exp.get("cbot", [])]
        rows += [[r["base"], "FX (no Form 4)", f(r["mt"]), "", "±1 EGP", f(r["egp_per_step"])] for r in exp.get("fx", [])]
        el += [Paragraph("Price exposure (EGP cost change per step; up = dearer)", h2),
               table(["Commodity", "Futures / FX", "MT", "Now", "Step", "EGP per step"], rows, [2.4, 3.0, 2.4, 2.2, 2.0, 3.0])]
    el += [Paragraph("Stock cover (configured daily rate)", h2),
           table(["Commodity", "In stock MT", "Outstanding MT", "Daily rate", "Consumed 7 days", "Days (stock)", "Days (+ outstanding)"],
                 [[c["base"], f(c["stock_mt"]), f(c["outstanding_mt"]), f(c["daily_rate"]), f(c["consumed_7d"]), f(c["cover_days"], 1) if c["stock_mt"] else "—",
                   f(c["cover_days_incl_outstanding"], 1) if (c["stock_mt"] + c["outstanding_mt"]) else "no stock on record"]
                  for c in brief["cover"]], [2.4, 2.4, 2.6, 2.2, 2.6, 2.4, 3.0])]
    sl = brief["since_last"] or {}
    if sl.get("previous"):
        el += [Paragraph(f"Since the last report ({sl['previous'].get('generated')})", h2),
               table(["Figure", "Previous", "Now", "Change"],
                     [[r["label"], f(r["previous"], 2 if "CBOT" in r["label"] or "FX" in r["label"] else 0),
                       f(r["now"], 2 if "CBOT" in r["label"] or "FX" in r["label"] else 0),
                       f(r["change"], 2 if "CBOT" in r["label"] or "FX" in r["label"] else 0, True)] for r in sl["rows"]],
                     [7.0, 3.0, 3.0, 3.0], colour_cols=())]
    if brief["fixes"]:
        el += [Paragraph(f"Data to fix — {len(brief['fixes'])} high/medium of {brief['fixes_total']}", h2),
               table(["Severity", "Issue", "Contract", "Detail", "What to do"],
                     [[x["severity"], x["category"], x["contract"] or "—", x["detail"], x["action"]] for x in brief["fixes"][:10]],
                     [1.6, 3.6, 3.4, 9.0, 7.6])]
        if len(brief["fixes"]) > 10:
            el += [Paragraph(f"… and {len(brief['fixes']) - 10} more — see the Watch List sheet of the Excel brief or "
                             "“Data to fix…” in the app.", small)]
    doc.build(el)
    return path

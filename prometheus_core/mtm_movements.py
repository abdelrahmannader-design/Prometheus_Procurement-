"""Every daily Open-MTM movement of every contract, from the day it was stored to today.

The Home screen's "Daily Open MTM Movement" table compares today's open book with the previous
stored day. This module produces that same comparison for every stored day in the ledger
(``open_mtm_daily``) and writes it to Excel:

* ``extend_to_storage`` rebuilds, for each contract, the trading days between its storage start
  and its first stored record (it was in the warehouse before it was entered in the app). The
  rows come from the CBOT close, the FX history and the local price of each day, with the fees,
  premium and tonnes of the contract's first record. They are marked RECONSTRUCTED and are used
  only for the export; the stored ledger is not changed.
* ``day_blocks`` repeats the Home table for each stored day against the previous stored day:
  one row per contract (new and exited contracts included, the same way Home shows them) and
  the open-book total with the tonne-weighted reasons.
* ``contract_trails`` gives each contract's own day-by-day trail against its own previous day.
* ``write_movements_excel`` writes Summary, Book by Day, Daily Movement, Contract Trail and one
  sheet per open contract whose movement columns are live formulas.

The split of the change in Sav/MT is the one used on Home (``mtm_attribution``):
from CBOT = −ΔCIF × prior FX, from FX = −today's CIF × ΔFX, from Local = Δ local, Other = rest.
"""
from __future__ import annotations

import datetime as dt
import re

from .mtm_attribution import attribute
from .mtm_history import rebuild_row

PARTS = ("from_cbot", "from_fx", "from_local", "other")


def _n(v):
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def _sub(a, b):
    return a - b if None not in (a, b) else None


def _base(r):
    return (r.get("base_commodity") or r.get("commodity") or "").upper().split("-")[0]


def _rows(history):
    return [r for r in history or [] if isinstance(r, dict) and r.get("date") and r.get("contract_id")]


def storage_start(contract):
    """The contract's storage start date (YYYY-MM-DD) or ''."""
    v = str((contract or {}).get("storage_start") or "")[:10]
    try:
        dt.date.fromisoformat(v)
        return v
    except ValueError:
        return ""


def first_records(history):
    """{contract_id: its first stored record}."""
    out = {}
    for r in sorted(_rows(history), key=lambda x: x["date"]):
        out.setdefault(r["contract_id"], r)
    return out


def extend_to_storage(history, contracts, trading_days, cbot_on, fx_on, local_on, ids=None, captured_at=""):
    """Rows for the trading days from each contract's storage start up to (not incl.) its first record.

    Returns the new rows; ``history`` is not changed. A contract without a storage start, or whose
    first record is on or before it, gets none.
    """
    out = []
    days = sorted(set(trading_days or []))
    for cid, first in sorted(first_records(history).items()):
        if ids is not None and cid not in ids:
            continue
        c = (contracts or {}).get(cid) or {}
        start = storage_start(c)
        if not start or start >= first["date"]:
            continue
        for day in days:
            if start <= day < first["date"]:
                rec = rebuild_row(day, first, c, cbot_on, fx_on, local_on, captured_at)
                rec["capture_reason"] = "before_first_record"
                rec["reconstructed_from"] = (rec.get("reconstructed_from", "") +
                                             f"; before the contract was entered (storage start {start})")
                out.append(rec)
    return out


def excl_transport(history, contracts, local_transport_on):
    """Copies of the records on the excluding-transport basis, the way Home computes it.

    Our price loses the contract's route freight; the local price loses the transport recorded on
    its quote (``local_transport_on(contract, record)`` → EGP/MT, None when unknown). Saving and
    total follow. The including-transport values are kept as ``*_incl`` and the two transport
    amounts as ``freight_egp_mt`` / ``local_transport_egp_mt``.
    """
    out = []
    for r in history or []:
        if not isinstance(r, dict):
            continue
        x = dict(r)
        loc, own, q = _n(r.get("local_egp_mt")), _n(r.get("own_after_egp_mt")), _n(r.get("qty_mt"))
        fr = _n(r.get("freight_egp_mt")) or 0.0
        lt = local_transport_on((contracts or {}).get(r.get("contract_id")) or r, r) if loc is not None else None
        lt = _n(lt)
        le = round(loc - lt, 4) if None not in (loc, lt) else None
        oe = round(own - fr, 4) if own is not None else None
        se = round(le - oe, 4) if None not in (le, oe) else None
        x.update({"local_incl_egp_mt": loc, "own_incl_egp_mt": own, "saving_incl_egp_mt": _n(r.get("saving_egp_mt")),
                  "total_incl_egp": _n(r.get("total_saving_egp")), "local_transport_egp_mt": lt,
                  "local_egp_mt": le, "own_after_egp_mt": oe, "saving_egp_mt": se,
                  "total_saving_egp": round(se * q, 2) if None not in (se, q) else None, "basis": "excl"})
        if loc is not None and lt is None:
            x["stale_quotes"] = list(r.get("stale_quotes") or []) + ["no transport found on the local quote"]
        out.append(x)
    return out


def contract_trails(history, ids=None):
    """{contract_id: [rows in date order]}; each row against the contract's own previous day."""
    by = {}
    for r in sorted(_rows(history), key=lambda x: (x["contract_id"], x["date"])):
        if ids is None or r["contract_id"] in ids:
            by.setdefault(r["contract_id"], []).append(r)
    out = {}
    for cid, rs in by.items():
        trail, p = [], None
        for r in rs:
            a = attribute(r, p) if p else {k: None for k in PARTS + ("change",)}
            trail.append({"rec": r, "prior": p, "why": a})
            p = r
        out[cid] = trail
    return out


def _book(rows):
    """Home's open-book totals: (MT, total EGP, weighted Sav/MT = total / MT)."""
    qty = sum(_n(r.get("qty_mt")) or 0.0 for r in rows)
    vals = [_n(r.get("total_saving_egp")) for r in rows]
    total = sum(v for v in vals if v is not None) if any(v is not None for v in vals) else None
    return qty, total, (total / qty if total is not None and qty else None)


def day_blocks(history, ids=None):
    """The Home comparison for every stored day against the previous stored day.

    Returns [{"date", "prior_date", "rows": [...], "book": {...}}] in date order. Row keys follow the
    Home table: ref, contract_id, commodity, flag (''/new/exited), mt, cbot / cbot_prior / d_cbot,
    sav / sav_prior / d_sav, from_cbot, from_fx, from_local, other, total / total_prior / d_total,
    plus cif, fx, local (today and prior), local_date, mode, stale and note.
    """
    by_date = {}
    for r in _rows(history):
        if ids is None or r["contract_id"] in ids:
            by_date.setdefault(r["date"], {})[r["contract_id"]] = r
    out, prior_date = [], ""
    for day in sorted(by_date):
        cur, prv = by_date[day], by_date.get(prior_date, {})
        keys = sorted(set(cur) | set(prv), key=lambda k: (_base(cur.get(k) or prv.get(k)),
                                                         (cur.get(k) or prv.get(k)).get("contract_ref") or k))
        rows, wsum, wq = [], dict.fromkeys(PARTS, 0.0), 0.0
        for cid in keys:
            c, p = cur.get(cid), prv.get(cid)
            a = c or p
            why = attribute(c, p) if (c and p) else {}
            g = lambda rec, k: _n((rec or {}).get(k))
            d_sav, d_tot = _sub(g(c, "saving_egp_mt"), g(p, "saving_egp_mt")), _sub(g(c, "total_saving_egp"), g(p, "total_saving_egp"))
            flag = ""
            if c is None:
                flag = "exited"
                d_sav = -g(p, "saving_egp_mt") if g(p, "saving_egp_mt") is not None else None
                d_tot = -g(p, "total_saving_egp") if g(p, "total_saving_egp") is not None else None
            elif p is None and prior_date:
                flag = "new"
                d_sav, d_tot = g(c, "saving_egp_mt"), g(c, "total_saving_egp")
            q = g(c, "qty_mt") or 0.0
            if why and all(why.get(k) is not None for k in PARTS) and q:
                wq += q
                for k in PARTS:
                    wsum[k] += why[k] * q
            rows.append({
                "date": day, "prior_date": prior_date, "contract_id": cid, "ref": a.get("contract_ref") or cid,
                "commodity": a.get("base_commodity") or a.get("commodity") or "", "supplier": a.get("supplier") or "",
                "flag": flag, "mt": g(c, "qty_mt") if c else g(p, "qty_mt"),
                "cbot": g(c, "cbot_price"), "cbot_prior": g(p, "cbot_price"), "d_cbot": _sub(g(c, "cbot_price"), g(p, "cbot_price")),
                "sav": g(c, "saving_egp_mt"), "sav_prior": g(p, "saving_egp_mt"), "d_sav": d_sav,
                **{k: why.get(k) for k in PARTS},
                "total": g(c, "total_saving_egp"), "total_prior": g(p, "total_saving_egp"), "d_total": d_tot,
                "cif": g(c, "cif_usd_mt"), "cif_prior": g(p, "cif_usd_mt"), "fx": g(c, "fx"), "fx_prior": g(p, "fx"),
                "fx_source": (c or {}).get("fx_source", ""), "local": g(c, "local_egp_mt"), "local_prior": g(p, "local_egp_mt"),
                "local_date": (c or {}).get("local_price_date", ""), "own": g(c, "own_after_egp_mt"),
                "freight": g(c, "freight_egp_mt"), "local_transport": g(c, "local_transport_egp_mt"),
                "mode": "Rebuilt" if (c or {}).get("mode") == "RECONSTRUCTED" else ("Live" if c else ""),
                "stale": "; ".join((c or {}).get("stale_quotes") or []), "note": (c or {}).get("reconstructed_from", ""),
            })
            if c and p and (g(c, "total_saving_egp") is None) != (g(p, "total_saving_egp") is None):
                gap = day if g(c, "total_saving_egp") is None else prior_date
                rows[-1]["note"] = (f"no saving on {gap} (a price was missing); the book total that day leaves it out"
                                    + ("; " + rows[-1]["note"] if rows[-1]["note"] else ""))
        q1, t1, s1 = _book(list(cur.values()))
        q0, t0, s0 = _book(list(prv.values()))
        cbot = {}
        for side, recs in (("today", cur), ("prior", prv)):
            for r in recs.values():
                b = _base(r)
                if _n(r.get("cbot_price")) is not None and (b, side) not in cbot:
                    cbot[(b, side)] = (_n(r.get("cbot_price")), r.get("cbot_unit") or "")
        bases = sorted({b for b, _s in cbot})
        book = {
            "contracts": len(cur), "contracts_prior": len(prv), "mt": q1, "mt_prior": q0,
            "total": t1, "total_prior": t0 if prior_date else None, "d_total": _sub(t1, t0) if prior_date else None,
            "sav": s1, "sav_prior": s0 if prior_date else None, "d_sav": _sub(s1, s0) if prior_date else None,
            **{k: (wsum[k] / wq if wq else None) for k in PARTS},
            "cbot": {b: ((cbot.get((b, "today")) or (None,))[0], (cbot.get((b, "prior")) or (None,))[0]) for b in bases},
            "units": {b: (cbot.get((b, "today")) or cbot.get((b, "prior")) or (None, ""))[1] for b in bases},
            "mode": _mode({r.get("mode") for r in cur.values()}),
            "prior_mode": _mode({r.get("mode") for r in prv.values()}) if prv else "",
            "stale": "; ".join(sorted({s for r in cur.values() for s in (r.get("stale_quotes") or [])})),
        }
        book["excl"] = any(r.get("basis") == "excl" for r in cur.values())
        book["text"] = headline(day, prior_date, book)
        out.append({"date": day, "prior_date": prior_date, "rows": rows, "book": book})
        prior_date = day
    return out


def _mode(modes):
    modes = {m or "LIVE" for m in modes}
    return "Live" if modes <= {"LIVE"} else "Rebuilt" if modes == {"RECONSTRUCTED"} else "Mixed"


def _sg(v, d=0):
    return "—" if v is None else f"{v:+,.{d}f}".replace("-", "−")


def headline(day, prior_date, b):
    """The Home summary line, e.g. '2026-11-09 → 2026-11-10 · Open MTM edge EGP 6,959,716 → …'."""
    money = lambda v: "—" if v is None else f"EGP {v:,.0f}"
    if not prior_date:
        return f"{day} · first stored day · {b['contracts']} contracts, {b['mt']:,.0f} MT, Open MTM edge {money(b['total'])}"
    bits = [f"{prior_date} → {day}",
            f"Open MTM edge{' excl transport' if b.get('excl') else ''} {money(b['total_prior'])} → {money(b['total'])} (Δ {_sg(b['d_total'])})",
            f"Weighted Saving/MT Δ {_sg(b['d_sav'])}"]
    for base, (t, p) in b["cbot"].items():
        if t is not None and p is not None:
            bits.append(f"{base} {p:,.2f}→{t:,.2f}")
    if b["from_cbot"] is not None:
        bits.append("Why (EGP/MT, tonne-weighted): " + " · ".join(
            f"{lab} {_sg(b[k])}" for k, lab in (("from_cbot", "CBOT"), ("from_fx", "FX"), ("from_local", "local"), ("other", "other"))))
    if b["prior_mode"] in ("Rebuilt", "Mixed"):
        bits.append(f"{prior_date} was rebuilt from stored closes")
    return " · ".join(bits)


# ── Excel ────────────────────────────────────────────────────────────────

NAVY, GREEN, RED, GREY, AMBER = "1F3A5F", "1A7A1A", "B3261E", "6B7280", "9A6B00"
F0, F2, F4 = "#,##0;-#,##0", "#,##0.00;-#,##0.00", "0.0000"
S0, S2 = "[>=0.5]+#,##0;[<=-0.5]-#,##0;0", "[>=0.005]+#,##0.00;[<=-0.005]-#,##0.00;0.00"
REBUILT_FILL, TOTAL_FILL, NEW_FILL = "F3F0FF", "E8EEF6", "FFF7E0"


def sheet_name(ref, used):
    """A valid, unique sheet name for a contract reference."""
    base = re.sub(r"[\[\]\*\?/\\:]", "-", str(ref or "Contract")).strip("' ")[:28] or "Contract"
    name, i = base, 2
    while name.lower() in used:
        name = f"{base[:25]}~{i}"
        i += 1
    used.add(name.lower())
    return name


INPUT_FILL = "FFFBEA"     # light yellow: an input value; every other number is a formula
EPOCH = dt.date(1899, 12, 30)


def _date(v):
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _serial(d):
    return (d - EPOCH).days if d else None


def incl_view(r):
    """A record put through ``excl_transport`` back on the including-transport basis."""
    if r.get("basis") != "excl":
        return r
    x = dict(r)
    x.update({"local_egp_mt": r.get("local_incl_egp_mt"), "own_after_egp_mt": r.get("own_incl_egp_mt"),
              "saving_egp_mt": r.get("saving_incl_egp_mt"), "total_saving_egp": r.get("total_incl_egp"), "basis": "incl"})
    return x


def row_inputs(r):
    """The input values one formula row is built from (incl-transport local and our price)."""
    excl = r.get("basis") == "excl"
    cbot, prem, conv, cif = (_n(r.get(k)) for k in ("cbot_price", "premium_quote", "cbot_conversion", "cif_usd_mt"))
    floating = None not in (cbot, prem, conv, cif) and abs(cif - (cbot + prem) * conv) < 0.01
    fixed = None if floating else cif
    calc_cif = (cbot + prem) * conv if floating else cif
    fx, disc, clr, fr = _n(r.get("fx")), _n(r.get("discharge_egp_mt")), _n(r.get("clearance_egp_mt")), _n(r.get("freight_egp_mt"))
    own = _n(r.get("own_incl_egp_mt") if excl else r.get("own_after_egp_mt"))
    other = (own - (calc_cif * fx + (disc or 0) + (clr or 0) + (fr or 0))) if None not in (own, calc_cif, fx) else None
    return {"cid": r["contract_id"], "ref": r.get("contract_ref") or r["contract_id"], "base": _base(r),
            "date": _date(r["date"]), "mode": "Rebuilt" if r.get("mode") == "RECONSTRUCTED" else "Live",
            "mt": _n(r.get("qty_mt")), "cbot": cbot, "prem": prem if floating else None, "factor": conv if floating else None,
            "fixed_cif": fixed, "fx": fx, "fx_source": r.get("fx_source", ""), "disc": disc, "clr": clr, "other_fee": other,
            "freight": fr, "local_incl": _n(r.get("local_incl_egp_mt") if excl else r.get("local_egp_mt")),
            "local_tr": _n(r.get("local_transport_egp_mt")), "local_date": _date(r.get("local_price_date")),
            "stale": "; ".join(r.get("stale_quotes") or []), "note": r.get("reconstructed_from", "")}


def chain(rows, excl):
    """The values the trail formulas give, row by row (``rows`` from ``row_inputs``, contracts contiguous)."""
    out, prev, first = [], None, {}
    for x in rows:
        same = prev is not None and prev["cid"] == x["cid"]
        p = prev if same else None
        y = dict(x)
        if x["fixed_cif"] is not None:
            cif = x["fixed_cif"]
        elif None not in (x["cbot"], x["prem"], x["factor"]):
            cif = (x["cbot"] + x["prem"]) * x["factor"]
        else:
            cif = None
        own_i = (cif * x["fx"] + (x["disc"] or 0) + (x["clr"] or 0) + (x["other_fee"] or 0) + (x["freight"] or 0)
                 if None not in (cif, x["fx"]) else None)
        cif_egp = cif * x["fx"] if None not in (cif, x["fx"]) else None
        own_x = (cif_egp + (x["disc"] or 0) + (x["clr"] or 0) + (x["other_fee"] or 0)) if cif_egp is not None else None
        loc_x = x["local_incl"] - x["local_tr"] if None not in (x["local_incl"], x["local_tr"]) else None
        loc, own = (loc_x, own_x) if excl else (x["local_incl"], own_i)
        sav = loc - own if None not in (loc, own) else None
        tot = sav * x["mt"] if None not in (sav, x["mt"]) else None
        y.update(prior_date=p["date"] if p else None, cif=cif, cif_egp=cif_egp, own_incl=own_i, own_excl=own_x, local_excl=loc_x,
                 local=loc, own=own, sav=sav, total=tot,
                 d_cbot=_sub(x["cbot"], p["cbot"]) if p else None, d_sav=_sub(sav, p["sav"]) if p else None,
                 from_cbot=(-(cif - p["cif"]) * p["fx"]) if p and None not in (cif, p["cif"], p["fx"]) else None,
                 from_fx=(-cif * (x["fx"] - p["fx"])) if p and None not in (cif, x["fx"], p["fx"]) else None,
                 from_local=_sub(loc, p["local"]) if p else None, d_total=_sub(tot, p["total"]) if p else None)
        parts = [y["d_sav"], y["from_cbot"], y["from_fx"], y["from_local"]]
        y["other"] = parts[0] - parts[1] - parts[2] - parts[3] if None not in parts else None
        if x["cid"] not in first:
            first[x["cid"]] = y
        y["cum"] = _sub(sav, first[x["cid"]]["sav"])
        y["key"] = f"{x['cid']}|{_serial(x['date'])}"
        out.append(y)
        prev = y
    return out


# Trail columns (Contract Trail and the per-contract sheets share them).
TR_HEADS = ["Ref", "Contract ID", "Commodity", "Date", "Prior date", "Record", "MT", "CBOT", "Δ CBOT", "Premium",
            "Factor", "Fixed CIF $/MT", "CIF $/MT", "FX", "FX source", "CIF EGP/MT", "Discharge", "Clearance", "Other fees", "Our freight",
            "Our price incl tr.", "Our price excl tr.", "Local incl tr.", "Local transport", "Local excl tr.", "Local date",
            "Sav/MT", "Δ Sav/MT", "from CBOT", "from FX", "from Local", "Other", "Total EGP", "Δ Total", "Cumulative Δ Sav/MT",
            "Key", "Old quotes", "How it was rebuilt"]
TR_W = [16, 10, 10, 11, 11, 8, 9, 9, 8, 8, 8, 9, 9, 8, 14, 10, 9, 9, 8, 9, 11, 11, 10, 9, 10, 11, 10, 9, 9, 8, 9, 8, 13, 12,
        11, 14, 22, 60]
TC = {h: i + 1 for i, h in enumerate(TR_HEADS)}


def write_movements_excel(history, contracts, path, as_of=None, ids=None, scope_label="All contracts",
                          extension=None, ledger_start=None, basis="incl"):
    """Write the workbook; ``history`` should already include ``extension`` rows if they are wanted.

    Input prices are values (yellow); everything derived from them is a formula: CIF, our price, local
    excluding transport, saving, total, every change and its split, the open book of every day (SUMIFS
    over the Daily Movement rows, which look their values up in the Contract Trail) and the summary.
    ``basis``: "excl" compares local and our price without transport (records must have gone through
    ``excl_transport``), "incl" with it. Returns a dict with the counts written.
    """
    from openpyxl import Workbook
    from openpyxl.chart import LineChart, Reference
    from openpyxl.formatting.rule import CellIsRule
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter as L
    from openpyxl.worksheet.table import Table, TableStyleInfo

    from .xlsx_cache import store_formula_results

    excl = basis == "excl"
    tag = " (excl tr.)" if excl else " (incl tr.)"
    contracts = contracts or {}
    rows_all = [r if excl else incl_view(r) for r in _rows(history)]
    if ledger_start is None:
        ledger_start = min((r["date"] for r in rows_all if r.get("capture_reason") != "before_first_record"), default="")
    blocks = day_blocks(rows_all, ids)
    trails = contract_trails(rows_all, ids)
    as_of = as_of or (blocks[-1]["date"] if blocks else dt.date.today().isoformat())
    last_day = blocks[-1]["date"] if blocks else ""
    open_now = {cid for cid in trails if trails[cid][-1]["rec"]["date"] == last_day
                and str(contracts.get(cid, {}).get("status") or "Open").lower() != "closed"}

    wb = Workbook()
    cache = {}
    fill_in = PatternFill("solid", fgColor=INPUT_FILL)

    def put(ws, r, c, v, fmt=None, bold=False, color=None, fill=None, italic=False, size=None, inp=False):
        cell = ws.cell(r, c, v)
        if fmt:
            cell.number_format = fmt
        if bold or color or italic or size:
            cell.font = Font(bold=bold, color=color, italic=italic, size=size)
        if fill:
            cell.fill = PatternFill("solid", fgColor=fill)
        elif inp and v is not None:
            cell.fill = fill_in
        return cell

    def f(ws, r, c, formula, value, fmt=None, **kw):
        put(ws, r, c, formula, fmt, **kw)
        if isinstance(value, dt.date):
            value = _serial(value)
        cache.setdefault(ws.title, {})[f"{L(c)}{r}"] = "" if value is None else value

    def title(ws, text, sub):
        put(ws, 1, 1, text, bold=True, size=15, color=NAVY)
        put(ws, 2, 1, sub, italic=True, color=GREY)

    def table(ws, name, heads, widths, n, hr=4):
        for i, h in enumerate(heads, start=1):
            c = ws.cell(hr, i, h)
            c.alignment = Alignment(wrap_text=True, vertical="center")
            ws.column_dimensions[L(i)].width = widths[i - 1]
        ws.row_dimensions[hr].height = 32
        t = Table(displayName=name, ref=f"A{hr}:{L(len(heads))}{hr + max(n, 1)}")
        t.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
        ws.add_table(t)

    def signs(ws, ref):
        ws.conditional_formatting.add(ref, CellIsRule(operator="lessThan", formula=["0"], font=Font(color=RED)))
        ws.conditional_formatting.add(ref, CellIsRule(operator="greaterThan", formula=["0"], font=Font(color=GREEN)))

    def isn(*cells):
        return "AND(" + ",".join(f"ISNUMBER({c})" for c in cells) + ")"

    DF = "yyyy-mm-dd"
    n_ext = len(extension or [])
    period = f"{blocks[0]['date']} → {last_day}" if blocks else "—"
    sub = (("PRICES EXCL TRANSPORT · " if excl else "Prices incl transport · ") + f"{scope_label} · {period} · as of {as_of}"
           f" · ledger started {ledger_start or '—'}"
           + (f" · {n_ext} contract-days before entry rebuilt back to the storage start" if n_ext else "")
           + " · yellow = input, everything else is a formula")

    order = sorted(trails, key=lambda k: (k not in open_now, _base(trails[k][-1]["rec"]), trails[k][0]["rec"]["date"],
                                          trails[k][-1]["rec"].get("contract_ref") or k))
    used = {"summary", "book by day", "daily movement", "contract trail"}
    sheets = {cid: sheet_name(trails[cid][-1]["rec"].get("contract_ref") or cid, used) for cid in order if cid in open_now}

    # ── the trail rows: inputs and the formula chain (Contract Trail and per-contract sheets) ──
    tl = lambda h: L(TC[h])
    LOC_H, OWN_H = ("Local excl tr.", "Our price excl tr.") if excl else ("Local incl tr.", "Our price incl tr.")
    fm_tr = {"MT": F0, "CBOT": F2, "Δ CBOT": S2, "Premium": F2, "Factor": F4, "Fixed CIF $/MT": F2, "CIF $/MT": F2,
             "FX": F4, "CIF EGP/MT": F0, "Discharge": F0, "Clearance": F0, "Other fees": F0, "Our freight": F0,
             "Our price incl tr.": F0, "Our price excl tr.": F0, "Local incl tr.": F0, "Local transport": F0,
             "Local excl tr.": F0, "Sav/MT": F0, "Δ Sav/MT": S0, "from CBOT": S0, "from FX": S0, "from Local": S0,
             "Other": S0, "Total EGP": F0, "Δ Total": S0, "Cumulative Δ Sav/MT": S0, "Date": DF, "Prior date": DF,
             "Local date": DF}

    def trail_heads():
        return [h + tag if h in ("Sav/MT", "Total EGP") else h for h in TR_HEADS]

    def write_trail(ws, start, ys):
        """Rows from ``start``; returns the last row."""
        firsts = {}
        for i, y in enumerate(ys):
            r, q = start + i, start + i - 1
            firsts.setdefault(y["cid"], r)
            fr0 = firsts[y["cid"]]
            same = f"$B{r}=$B{q}"
            col = lambda h: TC[h]
            a = lambda h, row=None: f"{tl(h)}{r if row is None else row}"
            for h, v in (("Ref", y["ref"]), ("Contract ID", y["cid"]), ("Commodity", y["base"]), ("Date", y["date"]),
                         ("Record", y["mode"]), ("MT", y["mt"]), ("CBOT", y["cbot"]), ("Premium", y["prem"]),
                         ("Factor", y["factor"]), ("Fixed CIF $/MT", y["fixed_cif"]), ("FX", y["fx"]),
                         ("FX source", y["fx_source"]), ("Discharge", y["disc"]), ("Clearance", y["clr"]),
                         ("Other fees", y["other_fee"]), ("Our freight", y["freight"]), ("Local incl tr.", y["local_incl"]),
                         ("Local transport", y["local_tr"]), ("Local date", y["local_date"]), ("Old quotes", y["stale"]),
                         ("How it was rebuilt", y["note"])):
                put(ws, r, col(h), v, fm_tr.get(h), inp=h in ("Date", "MT", "CBOT", "Premium", "Factor", "Fixed CIF $/MT",
                                                             "FX", "Discharge", "Clearance", "Other fees", "Our freight",
                                                             "Local incl tr.", "Local transport"))
            if y["mode"] == "Rebuilt":
                ws.cell(r, col("Record")).fill = PatternFill("solid", fgColor=REBUILT_FILL)
            F = lambda h, formula, v: f(ws, r, col(h), formula, v, fm_tr.get(h))
            prev = lambda h: f'=IF(AND({same},ISNUMBER({a(h)}),ISNUMBER({a(h, q)})),{a(h)}-{a(h, q)},"")'
            F("Prior date", f'=IF({same},{a("Date", q)},"")', y["prior_date"])
            F("Δ CBOT", prev("CBOT"), y["d_cbot"])
            F("CIF $/MT", f'=IF(ISNUMBER({a("Fixed CIF $/MT")}),{a("Fixed CIF $/MT")},IF({isn(a("CBOT"), a("Premium"), a("Factor"))},'
                          f'({a("CBOT")}+{a("Premium")})*{a("Factor")},""))', y["cif"])
            F("CIF EGP/MT", f'=IF({isn(a("CIF $/MT"), a("FX"))},{a("CIF $/MT")}*{a("FX")},"")', y["cif_egp"])
            F("Our price incl tr.", f'=IF(ISNUMBER({a("CIF EGP/MT")}),{a("CIF EGP/MT")}+{a("Discharge")}+{a("Clearance")}'
                                    f'+{a("Other fees")}+{a("Our freight")},"")', y["own_incl"])
            F("Our price excl tr.", f'=IF(ISNUMBER({a("CIF EGP/MT")}),{a("CIF EGP/MT")}+{a("Discharge")}+{a("Clearance")}'
                                    f'+{a("Other fees")},"")', y["own_excl"])
            F("Local excl tr.", f'=IF({isn(a("Local incl tr."), a("Local transport"))},{a("Local incl tr.")}-{a("Local transport")},"")',
              y["local_excl"])
            F("Sav/MT", f'=IF({isn(a(LOC_H), a(OWN_H))},{a(LOC_H)}-{a(OWN_H)},"")', y["sav"])
            F("Δ Sav/MT", prev("Sav/MT"), y["d_sav"])
            F("from CBOT", f'=IF(AND({same},ISNUMBER({a("CIF $/MT")}),ISNUMBER({a("CIF $/MT", q)}),ISNUMBER({a("FX", q)})),'
                           f'-({a("CIF $/MT")}-{a("CIF $/MT", q)})*{a("FX", q)},"")', y["from_cbot"])
            F("from FX", f'=IF(AND({same},ISNUMBER({a("CIF $/MT")}),ISNUMBER({a("FX")}),ISNUMBER({a("FX", q)})),'
                         f'-{a("CIF $/MT")}*({a("FX")}-{a("FX", q)}),"")', y["from_fx"])
            F("from Local", prev(LOC_H), y["from_local"])
            F("Other", f'=IF({isn(a("Δ Sav/MT"), a("from CBOT"), a("from FX"), a("from Local"))},'
                       f'{a("Δ Sav/MT")}-{a("from CBOT")}-{a("from FX")}-{a("from Local")},"")', y["other"])
            F("Total EGP", f'=IF({isn(a("Sav/MT"), a("MT"))},{a("Sav/MT")}*{a("MT")},"")', y["total"])
            F("Δ Total", prev("Total EGP"), y["d_total"])
            z0 = f"${tl('Sav/MT')}${fr0}"
            F("Cumulative Δ Sav/MT", f'=IF({isn(a("Sav/MT"), z0)},{a("Sav/MT")}-{z0},"")', y["cum"])
            F("Key", f'=$B{r}&"|"&TEXT($D{r},"0")', y["key"])
        return start + len(ys) - 1

    def trail_signs(ws, last):
        for a_, b_ in (("Δ CBOT", "Δ CBOT"), ("Δ Sav/MT", "Other"), ("Δ Total", "Cumulative Δ Sav/MT")):
            signs(ws, f"{tl(a_)}5:{tl(b_)}{last}")

    tr_inputs = [row_inputs(x["rec"]) for cid in order for x in trails[cid]]
    tr_vals = chain(tr_inputs, excl)
    by_key = {y["key"]: (i, y) for i, y in enumerate(tr_vals)}

    # ── Summary ──
    ws = wb.active
    ws.title = "Summary"
    title(ws, "Open MTM — every daily movement since storage" + (" (excl transport)" if excl else ""), sub)
    notes = [
        "Each day is compared with the previous stored day, exactly like the Home table \"Daily Open MTM Movement\". "
        "Δ Sav/MT is split into four parts that add up to it (EGP/MT):",
        "from CBOT = −(CIF today − CIF prior) × FX prior · from FX = −CIF today × (FX today − FX prior), 0 under Form 4 · "
        "from Local = local today − local prior · Other = the rest (discharge, clearance, fees).",
        "Contract Trail holds the inputs (yellow) and the formula chain: CIF = fixed CIF, else (CBOT + premium) × factor · "
        "our price incl tr. = CIF × FX + discharge + clearance + other fees + our freight · our price excl tr. = that − our "
        "freight · local excl tr. = local incl tr. − local transport · Sav/MT = local − our price · Total = Sav/MT × MT.",
        "Daily Movement shows the same build-up for today on every row: CIF $/MT × FX = CIF EGP/MT, + discharge + clearance + "
        "other fees (+ our freight) = our price excl (incl) transport, next to local incl tr., its transport and local excl tr.",
        "Daily Movement looks each contract up in the Contract Trail; Book by Day and the TOTAL rows add Daily Movement up "
        "(SUMIFS); this sheet reads the Contract Trail. Change an input and everything follows.",
        "Rebuilt = a day the app was not opened, or a day between the storage start and the day the contract was entered; "
        "rebuilt from the stored CBOT close, FX history and local price with the fees and tonnes of the nearest record. "
        "Book totals before the ledger started only hold the contracts entered later, so they are partial.",
        ("Basis: EXCLUDING transport: Sav/MT = local excl tr. − our price excl tr." if excl
         else "Basis: including transport, as on Home: Sav/MT = local incl tr. − our price incl tr."),
    ]
    for i, t in enumerate(notes):
        put(ws, 3 + i, 1, t, italic=True, color=GREY)
    hr = 11
    n_tr = len(tr_vals)
    T0, T1 = 5, 4 + max(n_tr, 1)
    TR = lambda h: f"'Contract Trail'!${L(TC[h])}${T0}:${L(TC[h])}${T1}"
    heads = ["Ref", "Contract ID", "Commodity", "Supplier", "Status", "Storage start", "Entered app", "Trail row",
             "Days", "First day", "Last day", "Rebuilt days", "MT", "CBOT first", "CBOT last", "Δ CBOT",
             "Sav/MT first" + tag, "Sav/MT last" + tag, "Δ Sav/MT", "from CBOT", "from FX", "from Local", "Other",
             "Total first" + tag, "Total last" + tag, "Δ Total", "Sheet"]
    table(ws, "ContractSummary", heads, [16, 10, 10, 16, 8, 11, 11, 8, 6, 11, 11, 8, 9, 9, 9, 8, 10, 10, 10, 9, 9, 9, 9,
                                         13, 13, 13, 14], len(order), hr=hr)
    pos = 0
    for i, cid in enumerate(order):
        r = hr + 1 + i
        ys = [y for y in tr_vals[pos:pos + len(trails[cid])]]
        first_row, n = pos + 1, len(ys)
        pos += n
        y0, y1 = ys[0], ys[-1]
        c = contracts.get(cid, {})
        put(ws, r, 1, y1["ref"]); put(ws, r, 2, cid, inp=True); put(ws, r, 3, y1["base"])
        put(ws, r, 4, trails[cid][-1]["rec"].get("supplier") or c.get("supplier") or "")
        put(ws, r, 5, "Open" if cid in open_now else (c.get("status") or "Closed"))
        put(ws, r, 6, _date(storage_start(c)), DF); put(ws, r, 7, _date(str(c.get("created_ts") or "")[:10]), DF)
        f(ws, r, 8, f"=MATCH(B{r},{TR('Contract ID')},0)", first_row)
        f(ws, r, 9, f"=COUNTIF({TR('Contract ID')},B{r})", n)
        last = f"H{r}+I{r}-1"
        ix = lambda h, at: f'IF(ISNUMBER(INDEX({TR(h)},{at})),INDEX({TR(h)},{at}),"")'
        f(ws, r, 10, f"=INDEX({TR('Date')},H{r})", y0["date"], DF)
        f(ws, r, 11, f"=INDEX({TR('Date')},{last})", y1["date"], DF)
        f(ws, r, 12, f'=COUNTIFS({TR("Contract ID")},B{r},{TR("Record")},"Rebuilt")', sum(1 for y in ys if y["mode"] == "Rebuilt"))
        f(ws, r, 13, "=" + ix("MT", last), y1["mt"], F0)
        f(ws, r, 14, "=" + ix("CBOT", f"H{r}"), y0["cbot"], F2)
        f(ws, r, 15, "=" + ix("CBOT", last), y1["cbot"], F2)
        f(ws, r, 16, f'=IF({isn(f"N{r}", f"O{r}")},O{r}-N{r},"")', _sub(y1["cbot"], y0["cbot"]), S2)
        f(ws, r, 17, "=" + ix("Sav/MT", f"H{r}"), y0["sav"], F0)
        f(ws, r, 18, "=" + ix("Sav/MT", last), y1["sav"], F0)
        f(ws, r, 19, f'=IF({isn(f"Q{r}", f"R{r}")},R{r}-Q{r},"")', _sub(y1["sav"], y0["sav"]), S0)
        for j, k in enumerate(PARTS):
            h = ("from CBOT", "from FX", "from Local", "Other")[j]
            f(ws, r, 20 + j, f"=SUMIFS({TR(h)},{TR('Contract ID')},B{r})", sum(y[k] or 0.0 for y in ys), S0)
        f(ws, r, 24, "=" + ix("Total EGP", f"H{r}"), y0["total"], F0)
        f(ws, r, 25, "=" + ix("Total EGP", last), y1["total"], F0)
        f(ws, r, 26, f'=IF({isn(f"X{r}", f"Y{r}")},Y{r}-X{r},"")', _sub(y1["total"], y0["total"]), S0)
        if cid in sheets:
            put(ws, r, 27, sheets[cid])
            ws.cell(r, 27).hyperlink = f"#'{sheets[cid]}'!A1"
            ws.cell(r, 27).font = Font(color="1F5FBF", underline="single")
    if order:
        signs(ws, f"P{hr + 1}:W{hr + len(order)}"); signs(ws, f"Z{hr + 1}:Z{hr + len(order)}")
    ws.freeze_panes = f"B{hr + 1}"

    wsb = wb.create_sheet("Book by Day")
    wsd = wb.create_sheet("Daily Movement")
    wst = wb.create_sheet("Contract Trail")

    # ── Contract Trail ──
    title(wst, "Contract trail — each contract against its own previous day" + (" (excl transport)" if excl else ""),
          sub + " · rows of a contract are together, oldest first; a change is against the row above when it is the same contract")
    table(wst, "ContractTrail", trail_heads(), TR_W, n_tr)
    write_trail(wst, 5, tr_vals)
    if tr_vals:
        trail_signs(wst, T1)
    wst.freeze_panes = "E5"

    # ── Daily Movement: every day as on Home, looked up in the Contract Trail ──
    title(wsd, "Daily Open MTM Movement — every day" + (" · excl transport" if excl else ", as on Home"),
          sub + " · newest day first · TOTAL rows are the open book of that day (Row = TOTAL to filter them)")
    SAVT, SAVP, TOTT, TOTP, LOCP = ("Sav/MT Today" + tag, "Sav/MT Prior" + tag, "Total Today" + tag, "Total Prior" + tag,
                                    "Local Prior" + tag)
    DH = ["Date", "Prior date", "Row", "Ref", "Contract ID", "Commodity", "Flag", "Trail row today", "Trail row prior",
          "MT Today", "MT Prior", "CBOT Today", "CBOT Prior", "Δ CBOT",
          # today's cost build-up and local price, both with and without transport
          "CIF $/MT", "FX", "CIF EGP/MT", "Discharge", "Clearance", "Other fees", "Our freight", "Our price incl tr.",
          "Our price excl tr.", "Local incl tr.", "Local transport", "Local excl tr.", "Local date",
          SAVT, SAVP, "Δ Sav/MT", "from CBOT", "from FX", "from Local", "Other", TOTT, TOTP, "Δ Total",
          "CIF Prior", "FX Prior", LOCP, "Record", "In today", "In prior", "Weight MT",
          "w × from CBOT", "w × from FX", "w × from Local", "w × Other", "Old quotes", "How it was rebuilt"]
    DC = {h: i + 1 for i, h in enumerate(DH)}
    dw = {"Date": 11, "Prior date": 11, "Row": 7, "Ref": 18, "Contract ID": 10, "Flag": 7, "Trail row today": 7,
          "Trail row prior": 7, "Δ CBOT": 8, "FX": 8, "FX Prior": 8, "Our price incl tr.": 11, "Our price excl tr.": 11,
          "Local incl tr.": 10, "Local excl tr.": 10, "Local date": 11, SAVT: 10, SAVP: 10, TOTT: 13, TOTP: 13,
          "Δ Total": 12, "In today": 6, "In prior": 6, "Old quotes": 22, "How it was rebuilt": 60}
    lines = []
    for blk in reversed(blocks):
        for x in blk["rows"]:
            lines.append(("row", blk, x))
        lines.append(("total", blk, None))
    D0, D1 = 5, 4 + max(len(lines), 1)
    table(wsd, "DailyMovement", DH, [dw.get(h, 9) for h in DH], len(lines))
    DR = lambda h: f"${L(DC[h])}${D0}:${L(DC[h])}${D1}"
    lc = {h: L(DC[h]) for h in DH}
    loc_h, own_h = ("Local excl tr.", "Our price excl tr.") if excl else ("Local incl tr.", "Our price incl tr.")
    look_today = [("MT Today", "MT", "mt", F0), ("CBOT Today", "CBOT", "cbot", F2), ("CIF $/MT", "CIF $/MT", "cif", F2),
                  ("FX", "FX", "fx", F4), ("Discharge", "Discharge", "disc", F0), ("Clearance", "Clearance", "clr", F0),
                  ("Other fees", "Other fees", "other_fee", F0), ("Our freight", "Our freight", "freight", F0),
                  ("Local incl tr.", "Local incl tr.", "local_incl", F0), ("Local transport", "Local transport", "local_tr", F0),
                  ("Local date", "Local date", "local_date", DF)]
    look_prior = [("MT Prior", "MT", "mt", F0), ("CBOT Prior", "CBOT", "cbot", F2), (SAVP, "Sav/MT", "sav", F0),
                  (TOTP, "Total EGP", "total", F0), ("CIF Prior", "CIF $/MT", "cif", F2), ("FX Prior", "FX", "fx", F4),
                  (LOCP, loc_h, "local", F0)]
    totals_by_date = {}
    dm_vals = []
    for i, (kind, blk, x) in enumerate(lines):
        r = 5 + i
        d1, d0 = _date(blk["date"]), _date(blk["prior_date"])
        put(wsd, r, DC["Date"], d1, DF, inp=True); put(wsd, r, DC["Prior date"], d0, DF, inp=True)
        if kind == "row":
            ti = by_key.get(f"{x['contract_id']}|{_serial(d1)}")
            pi = by_key.get(f"{x['contract_id']}|{_serial(d0)}") if d0 else None
            t, p = (ti[1] if ti else {}), (pi[1] if pi else {})
            v = {"t": t, "p": p}
            c_ = lambda h: f"{lc[h]}{r}"
            put(wsd, r, DC["Row"], "Contract"); put(wsd, r, DC["Ref"], x["ref"]); put(wsd, r, DC["Contract ID"], x["contract_id"])
            put(wsd, r, DC["Commodity"], x["commodity"]); put(wsd, r, DC["Flag"], x["flag"])
            if x["flag"]:
                wsd.cell(r, DC["Flag"]).fill = PatternFill("solid", fgColor=NEW_FILL)
            HT, HP = "$" + c_("Trail row today"), "$" + c_("Trail row prior")
            f(wsd, r, DC["Trail row today"], f'=IFERROR(MATCH($E{r}&"|"&TEXT($A{r},"0"),{TR("Key")},0),"")',
              ti[0] + 1 if ti else None)
            f(wsd, r, DC["Trail row prior"], f'=IF($B{r}="","",IFERROR(MATCH($E{r}&"|"&TEXT($B{r},"0"),{TR("Key")},0),""))',
              pi[0] + 1 if pi else None)
            for side, hc, spec in (("t", HT, look_today), ("p", HP, look_prior)):
                for h, th, k, fmt in spec:
                    val = v[side].get(k) if v[side] else None
                    f(wsd, r, DC[h], f'=IF(ISNUMBER({hc}),IF(ISNUMBER(INDEX({TR(th)},{hc})),INDEX({TR(th)},{hc}),""),"")',
                      val, fmt)
            g = lambda side, k: (v[side] or {}).get(k)
            # today's own price and saving are worked out here, on the row, from the looked-up inputs
            f(wsd, r, DC["CIF EGP/MT"], f'=IF({isn(c_("CIF $/MT"), c_("FX"))},{c_("CIF $/MT")}*{c_("FX")},"")', g("t", "cif_egp"), F0)
            fees = f'N({c_("Discharge")})+N({c_("Clearance")})+N({c_("Other fees")})'
            f(wsd, r, DC["Our price incl tr."], f'=IF(ISNUMBER({c_("CIF EGP/MT")}),{c_("CIF EGP/MT")}+{fees}+N({c_("Our freight")}),"")',
              g("t", "own_incl"), F0)
            f(wsd, r, DC["Our price excl tr."], f'=IF(ISNUMBER({c_("CIF EGP/MT")}),{c_("CIF EGP/MT")}+{fees},"")', g("t", "own_excl"), F0)
            f(wsd, r, DC["Local excl tr."], f'=IF({isn(c_("Local incl tr."), c_("Local transport"))},{c_("Local incl tr.")}-{c_("Local transport")},"")',
              g("t", "local_excl"), F0)
            f(wsd, r, DC[SAVT], f'=IF({isn(c_(loc_h), c_(own_h))},{c_(loc_h)}-{c_(own_h)},"")', g("t", "sav"), F0)
            f(wsd, r, DC[TOTT], f'=IF({isn(c_(SAVT), c_("MT Today"))},{c_(SAVT)}*{c_("MT Today")},"")', g("t", "total"), F0)
            rec_v = t.get("mode") if t else ""
            f(wsd, r, DC["Record"], f'=IF(ISNUMBER({HT}),INDEX({TR("Record")},{HT})&"","")', rec_v)
            if rec_v == "Rebuilt":
                wsd.cell(r, DC["Record"]).fill = PatternFill("solid", fgColor=REBUILT_FILL)
            d_cbot = _sub(g("t", "cbot"), g("p", "cbot"))
            if x["flag"] == "new":
                d_sav, d_tot = g("t", "sav"), g("t", "total")
            elif x["flag"] == "exited":
                d_sav = -g("p", "sav") if g("p", "sav") is not None else None
                d_tot = -g("p", "total") if g("p", "total") is not None else None
            else:
                d_sav, d_tot = _sub(g("t", "sav"), g("p", "sav")), _sub(g("t", "total"), g("p", "total"))
            c1, c0, f1, f0 = g("t", "cif"), g("p", "cif"), g("t", "fx"), g("p", "fx")
            fc = -(c1 - c0) * f0 if None not in (c1, c0, f0) else None
            ff = -c1 * (f1 - f0) if None not in (c1, f1, f0) else None
            fl = _sub(g("t", "local"), g("p", "local"))
            parts = [d_sav, fc, ff, fl]
            oth = parts[0] - fc - ff - fl if None not in parts else None
            CT, CP, XT, XP, LT, LP = c_("CIF $/MT"), c_("CIF Prior"), c_("FX"), c_("FX Prior"), c_(loc_h), c_(LOCP)
            f(wsd, r, DC["Δ CBOT"], f'=IF({isn(c_("CBOT Today"), c_("CBOT Prior"))},{c_("CBOT Today")}-{c_("CBOT Prior")},"")', d_cbot, S2)
            delta = lambda a_, b_: (f'=IF($G{r}="new",{a_},IF($G{r}="exited",IF(ISNUMBER({b_}),-{b_},""),'
                                    f'IF({isn(a_, b_)},{a_}-{b_},"")))')
            f(wsd, r, DC["Δ Sav/MT"], delta(c_(SAVT), c_(SAVP)), d_sav, S0)
            f(wsd, r, DC["from CBOT"], f'=IF({isn(CT, CP, XP)},-({CT}-{CP})*{XP},"")', fc, S0)
            f(wsd, r, DC["from FX"], f'=IF({isn(CT, XT, XP)},-{CT}*({XT}-{XP}),"")', ff, S0)
            f(wsd, r, DC["from Local"], f'=IF({isn(LT, LP)},{LT}-{LP},"")', fl, S0)
            f(wsd, r, DC["Other"], f'=IF({isn(c_("Δ Sav/MT"), c_("from CBOT"), c_("from FX"), c_("from Local"))},'
                                   f'{c_("Δ Sav/MT")}-{c_("from CBOT")}-{c_("from FX")}-{c_("from Local")},"")', oth, S0)
            f(wsd, r, DC["Δ Total"], delta(c_(TOTT), c_(TOTP)), d_tot, S0)
            in_t, in_p = (1 if ti else 0), (1 if pi else 0)
            f(wsd, r, DC["In today"], f'=IF(ISNUMBER({HT}),1,0)', in_t)
            f(wsd, r, DC["In prior"], f'=IF(ISNUMBER({HP}),1,0)', in_p)
            wq = g("t", "mt") if (None not in (fc, ff, fl, oth) and g("t", "mt")) else 0
            WM = c_("Weight MT")
            f(wsd, r, DC["Weight MT"], f'=IF(AND({isn(c_("from CBOT"), c_("from FX"), c_("from Local"), c_("Other"), c_("MT Today"))},'
                                       f'N({c_("MT Today")})<>0),{c_("MT Today")},0)', wq, F0)
            for h, src, val in (("w × from CBOT", "from CBOT", fc), ("w × from FX", "from FX", ff),
                                ("w × from Local", "from Local", fl), ("w × Other", "Other", oth)):
                f(wsd, r, DC[h], f'=IF({WM}<>0,{c_(src)}*{WM},0)', (val * wq) if wq else 0, F0)
            put(wsd, r, DC["Old quotes"], x["stale"]); put(wsd, r, DC["How it was rebuilt"], x["note"])
            dm_vals.append({"date": blk["date"], "commodity": x["commodity"], "mt_t": g("t", "mt"), "mt_p": g("p", "mt"),
                            "tot_t": g("t", "total"), "tot_p": g("p", "total"), "in_t": in_t, "in_p": in_p, "w": wq,
                            "parts": [(val * wq) if wq else 0 for val in (fc, ff, fl, oth)],
                            "cbot_t": g("t", "cbot"), "cbot_p": g("p", "cbot")})
        else:
            totals_by_date[blk["date"]] = r
    # TOTAL rows: SUMIFS over the contract rows of the same day
    agg = {}
    for v in dm_vals:
        a = agg.setdefault(v["date"], {"mt_t": 0.0, "mt_p": 0.0, "tot_t": 0.0, "tot_p": 0.0, "in_t": 0, "in_p": 0, "w": 0.0,
                                       "parts": [0.0] * 4, "cbot": {}})
        for k in ("mt_t", "mt_p", "tot_t", "tot_p", "in_t", "in_p", "w"):
            a[k] += v[k] or 0
        a["parts"] = [s + p for s, p in zip(a["parts"], v["parts"])]
        for side in ("t", "p"):
            if v["cbot_" + side] is not None:
                a["cbot"].setdefault((v["commodity"], side), []).append(v["cbot_" + side])

    def book_vals(day, prior):
        a = agg.get(day) or {"mt_t": 0.0, "mt_p": 0.0, "tot_t": 0.0, "tot_p": 0.0, "in_t": 0, "in_p": 0, "w": 0.0,
                             "parts": [0.0] * 4, "cbot": {}}
        sav_t = a["tot_t"] / a["mt_t"] if a["mt_t"] else None
        sav_p = a["tot_p"] / a["mt_p"] if (prior and a["mt_p"]) else None
        return {**a, "sav_t": sav_t, "sav_p": sav_p, "d_sav": _sub(sav_t, sav_p),
                "tot_p_b": a["tot_p"] if prior else None, "d_tot": (a["tot_t"] - a["tot_p"]) if prior else None,
                "why": [(s / a["w"]) if a["w"] else None for s in a["parts"]]}

    crit = lambda r: f'{DR("Date")},$A{r},{DR("Row")},"Contract"'
    for blk in blocks:
        r = totals_by_date[blk["date"]]
        bv = book_vals(blk["date"], blk["prior_date"])
        put(wsd, r, DC["Row"], "TOTAL", bold=True)
        S = lambda h: f"SUMIFS({DR(h)},{crit(r)})"
        f(wsd, r, DC["Ref"], f'="TOTAL OPEN BOOK ("&{S("In today")}&" today / "&{S("In prior")}&" prior)"',
          f"TOTAL OPEN BOOK ({bv['in_t']} today / {bv['in_p']} prior)", bold=True)
        f(wsd, r, DC["MT Today"], "=" + S("MT Today"), bv["mt_t"], F0, bold=True)
        f(wsd, r, DC["MT Prior"], "=" + S("MT Prior"), bv["mt_p"], F0, bold=True)
        f(wsd, r, DC["Total Today" + tag], "=" + S("Total Today" + tag), bv["tot_t"], F0, bold=True)
        f(wsd, r, DC["Total Prior" + tag], f'=IF($B{r}="","",{S("Total Prior" + tag)})', bv["tot_p_b"], F0, bold=True)
        J, K, V_, W_ = lc["MT Today"], lc["MT Prior"], lc["Total Today" + tag], lc["Total Prior" + tag]
        O_, P_ = lc[SAVT] + str(r), lc[SAVP] + str(r)
        f(wsd, r, DC["Sav/MT Today" + tag], f'=IF(N({J}{r})<>0,{V_}{r}/{J}{r},"")', bv["sav_t"], F0, bold=True)
        f(wsd, r, DC["Sav/MT Prior" + tag], f'=IF(AND($B{r}<>"",N({K}{r})<>0),{W_}{r}/{K}{r},"")', bv["sav_p"], F0, bold=True)
        f(wsd, r, DC["Δ Sav/MT"], f'=IF({isn(O_, P_)},{O_}-{P_},"")', bv["d_sav"], S0, bold=True)
        for j, (h, wh) in enumerate((("from CBOT", "w × from CBOT"), ("from FX", "w × from FX"),
                                     ("from Local", "w × from Local"), ("Other", "w × Other"))):
            f(wsd, r, DC[h], f'=IF({S("Weight MT")}<>0,{S(wh)}/{S("Weight MT")},"")', bv["why"][j], S0, bold=True)
        f(wsd, r, DC["Δ Total"], f'=IF($B{r}="","",{V_}{r}-{W_}{r})', bv["d_tot"], S0, bold=True)
        put(wsd, r, DC["Record"], blk["book"]["mode"], bold=True)
        put(wsd, r, DC["Old quotes"], blk["book"]["stale"]); put(wsd, r, DC["How it was rebuilt"], blk["book"]["text"])
        for cidx in range(1, len(DH) + 1):
            wsd.cell(r, cidx).fill = PatternFill("solid", fgColor=TOTAL_FILL)
            wsd.cell(r, cidx).font = Font(bold=True)
    if lines:
        for a_, b_ in (("Δ CBOT", "Δ CBOT"), ("Δ Sav/MT", "Other"), ("Δ Total", "Δ Total")):
            signs(wsd, f"{lc[a_]}5:{lc[b_]}{D1}")
    wsd.freeze_panes = "E5"

    # ── Book by Day: SUMIFS over the Daily Movement contract rows ──
    title(wsb, "Open book by day — the Home summary line for every day" + (" (excl transport)" if excl else ""), sub)
    bases = sorted({b for blk in blocks for b in blk["book"]["cbot"]})
    heads = ["Date", "Prior date", "Record", "Prior record", "Contracts", "Contracts prior", "MT", "Open MTM prior" + tag,
             "Open MTM today" + tag, "Δ Open MTM", "Sav/MT prior", "Sav/MT today", "Δ Sav/MT", "from CBOT", "from FX",
             "from Local", "Other", "Cumulative Δ Open MTM"]
    for b in bases:
        heads += [f"{b} prior", f"{b} today", f"Δ {b}"]
    heads += ["Partial book", "Old quotes", "Summary (as on Home)"]
    table(wsb, "BookByDay", heads, [11, 11, 8, 8, 8, 8, 10, 14, 14, 13, 9, 9, 9, 9, 8, 9, 8, 14] + [9, 9, 8] * len(bases)
          + [9, 24, 120], len(blocks))
    DMR = lambda h: f"'Daily Movement'!{DR(h)}"
    cum = 0.0
    for i, blk in enumerate(blocks):
        r, b = 5 + i, blk["book"]
        bv = book_vals(blk["date"], blk["prior_date"])
        cr = f'{DMR("Date")},$A{r},{DMR("Row")},"Contract"'
        S = lambda h: f"SUMIFS({DMR(h)},{cr})"
        put(wsb, r, 1, _date(blk["date"]), DF, inp=True); put(wsb, r, 2, _date(blk["prior_date"]), DF, inp=True)
        put(wsb, r, 3, b["mode"]); put(wsb, r, 4, b["prior_mode"])
        if b["mode"] != "Live":
            wsb.cell(r, 3).fill = PatternFill("solid", fgColor=REBUILT_FILL)
        f(wsb, r, 5, "=" + S("In today"), bv["in_t"])
        f(wsb, r, 6, f'=IF($B{r}="","",{S("In prior")})', bv["in_p"] if blk["prior_date"] else None)
        f(wsb, r, 7, "=" + S("MT Today"), bv["mt_t"], F0)
        f(wsb, r, 8, f'=IF($B{r}="","",{S("Total Prior" + tag)})', bv["tot_p_b"], F0)
        f(wsb, r, 9, "=" + S("Total Today" + tag), bv["tot_t"], F0)
        f(wsb, r, 10, f'=IF({isn(f"H{r}", f"I{r}")},I{r}-H{r},"")', bv["d_tot"], S0)
        f(wsb, r, 11, f'=IF(AND(ISNUMBER(H{r}),{S("MT Prior")}<>0),H{r}/{S("MT Prior")},"")', bv["sav_p"], F0)
        f(wsb, r, 12, f'=IF(G{r}<>0,I{r}/G{r},"")', bv["sav_t"], F0)
        f(wsb, r, 13, f'=IF({isn(f"K{r}", f"L{r}")},L{r}-K{r},"")', bv["d_sav"], S0)
        for j, wh in enumerate(("w × from CBOT", "w × from FX", "w × from Local", "w × Other")):
            f(wsb, r, 14 + j, f'=IF({S("Weight MT")}<>0,{S(wh)}/{S("Weight MT")},"")', bv["why"][j], S0)
        cum += bv["d_tot"] or 0.0
        f(wsb, r, 18, f"=SUM($J$5:J{r})", cum, S0)
        col = 19
        for base in bases:
            vals = {s: bv["cbot"].get((base, s)) for s in ("p", "t")}
            avg = {s: (sum(v) / len(v)) if v else None for s, v in vals.items()}
            for k, (s, h) in enumerate((("p", "CBOT Prior"), ("t", "CBOT Today"))):
                f(wsb, r, col + k, f'=IFERROR(AVERAGEIFS({DMR(h)},{cr},{DMR("Commodity")},"{base}"),"")', avg[s], F2)
            f(wsb, r, col + 2, f'=IF({isn(f"{L(col)}{r}", f"{L(col + 1)}{r}")},{L(col + 1)}{r}-{L(col)}{r},"")',
              _sub(avg["t"], avg["p"]), S2)
            col += 3
        put(wsb, r, col, "yes" if ledger_start and blk["date"] < ledger_start else "")
        put(wsb, r, col + 1, b["stale"]); put(wsb, r, col + 2, b["text"])
    if blocks:
        last = 4 + len(blocks)
        signs(wsb, f"J5:J{last}"); signs(wsb, f"M5:R{last}")
        ch = LineChart()
        ch.title, ch.height, ch.width = "Open MTM edge (EGP)" + tag, 8, 26
        ch.add_data(Reference(wsb, min_col=9, min_row=4, max_row=last), titles_from_data=True)
        ch.set_categories(Reference(wsb, min_col=1, min_row=5, max_row=last))
        ch.y_axis.numFmt = "#,##0"
        ch.legend = None
        wsb.add_chart(ch, f"A{last + 3}")
    wsb.freeze_panes = "B5"

    # ── one sheet per open contract: the same formula chain ──
    pos_of = {}
    p = 0
    for cid in order:
        pos_of[cid] = p
        p += len(trails[cid])
    for cid, name in sheets.items():
        ys = tr_vals[pos_of[cid]:pos_of[cid] + len(trails[cid])]
        c = contracts.get(cid, {})
        w = wb.create_sheet(name)
        y1 = ys[-1]
        title(w, f"{y1['ref']} · {y1['base']} · {trails[cid][-1]['rec'].get('supplier') or c.get('supplier') or ''}"
                 + (" · excl transport" if excl else ""),
              f"Contract {cid} · storage start {storage_start(c) or '—'} · entered {str(c.get('created_ts') or '')[:10] or '—'}"
              f" · {len(ys)} days · yellow = input, everything else is a formula (EGP/MT unless EGP)")
        table(w, "T_" + re.sub(r"\W", "_", cid), trail_heads(), TR_W, len(ys))
        last = write_trail(w, 5, ys)
        tr_row = last + 2
        put(w, tr_row, 1, "Since the first day", bold=True)
        for colx in range(1, len(TR_HEADS) + 1):
            w.cell(tr_row, colx).fill = PatternFill("solid", fgColor=TOTAL_FILL)
        f(w, tr_row, TC["Δ CBOT"], f'=IF({isn(tl("CBOT") + str(last), tl("CBOT") + "5")},{tl("CBOT")}{last}-{tl("CBOT")}5,"")', _sub(y1["cbot"], ys[0]["cbot"]), S2, bold=True)
        f(w, tr_row, TC["Δ Sav/MT"], f'=IF({isn(tl("Sav/MT") + str(last), tl("Sav/MT") + "5")},{tl("Sav/MT")}{last}-{tl("Sav/MT")}5,"")', _sub(y1["sav"], ys[0]["sav"]), S0, bold=True)
        for h, k in (("from CBOT", "from_cbot"), ("from FX", "from_fx"), ("from Local", "from_local"), ("Other", "other"),
                     ("Δ Total", "d_total")):
            cl = L(TC[h])
            f(w, tr_row, TC[h], f"=SUM({cl}5:{cl}{last})", sum(y[k] or 0.0 for y in ys), S0, bold=True)
        put(w, tr_row + 1, 1, "The four parts add up to Δ Sav/MT on every row; their sums add up to the change since "
                              "the first day when no day is missing a price.", italic=True, color=GREY)
        trail_signs(w, tr_row)
        w.freeze_panes = "E5"
        if len(ys) > 1:
            ch = LineChart()
            ch.title, ch.height, ch.width = "Sav/MT (EGP)" + tag, 7, 22
            ch.add_data(Reference(w, min_col=TC["Sav/MT"], min_row=4, max_row=last), titles_from_data=True)
            ch.set_categories(Reference(w, min_col=4, min_row=5, max_row=last))
            ch.legend = None
            w.add_chart(ch, f"A{tr_row + 3}")

    for s in wb.worksheets:
        s.page_setup.orientation = "landscape"
        s.page_setup.paperSize = s.PAPERSIZE_A4
        s.sheet_properties.pageSetUpPr.fitToPage = True
        s.page_setup.fitToWidth, s.page_setup.fitToHeight = 1, 0
        s.oddFooter.center.text = "&A · page &P of &N"
    wb.calculation.fullCalcOnLoad = True
    wb.save(path)
    store_formula_results(path, cache)
    return {"days": len(blocks), "contracts": len(trails), "open_sheets": len(sheets), "movement_rows": len(lines),
            "rebuilt_before_entry": n_ext, "basis": "excl" if excl else "incl",
            "formulas": sum(len(v) for v in cache.values()),
            "first_day": blocks[0]["date"] if blocks else "", "last_day": last_day}

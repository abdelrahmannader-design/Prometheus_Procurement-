"""Step-by-step workings for the Deal Evaluator (🧮 Calculate tab).

``build_workings`` turns the inputs and outputs of ``compute_decision`` into
numbered lines that show every multiplication with the real numbers, so a
reader can follow the CIF price, the finance carry (interest), the landed
cost, the saving and how finance days relate to the days the cargo sits in
inventory.  It only explains numbers that were already calculated; it never
changes a result.

Each line is ``(kind, text)`` with kind ``"h"`` (section heading), ``"f"``
(a formula with its result), ``"n"`` (a plain-language note), ``"k"`` (a key
result worth highlighting) or ``"x"`` (a key result that is adverse: a loss).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Any

from .numbers import to_float

DAY_BASIS = 360          # the app's finance convention (prometheus_core.cbot.carry_usd_mt)


def _n(x: Any, nd: int = 2) -> str:
    v = to_float(x, None)
    return "-" if v is None else f"{v:,.{nd}f}"


def _signed(x: float, nd: int = 2) -> str:
    return f"{x:+,.{nd}f}"


def cif_step(comm_meta: Mapping[str, Any], inp: Mapping[str, Any], import_usd_mt: float) -> list[tuple[str, str]]:
    """How the import price per MT was formed, mirroring ``cbot_to_usd_mt``."""
    if (comm_meta or {}).get("type", "NONCBOT") != "CBOT":
        if inp.get("import_usd_mt") not in (None, ""):
            return [("f", f"CIF price entered = {_n(import_usd_mt)} USD/MT")]
        egp = to_float(inp.get("import_egp_mt"), 0.0) or 0.0
        return [("f", f"CIF = import EGP/MT ÷ FX = {_n(egp)} ÷ {_n(inp.get('fx'), 4)} = {_n(import_usd_mt)} USD/MT")]
    cbot = to_float(inp.get("cbot"), 0.0) or 0.0
    prem = to_float(inp.get("premium_usd_mt"), 0.0) or 0.0
    locked = to_float(comm_meta.get("locked_factor"), None)
    if locked is not None:
        return [("f", f"CIF = (CBOT + premium) × factor = ({_n(cbot)} + {_n(prem)}) × {locked:g} "
                      f"= {_n(import_usd_mt)} USD/MT")]
    kind = comm_meta.get("conversion_type", "none")
    val = to_float(comm_meta.get("conversion_value"), 1.0) or 1.0
    cents_prem = comm_meta.get("premium_mode") == "CBOT_UNIT"
    if kind == "bu_per_mt" and cents_prem:
        txt = f"CIF = (CBOT + premium) ÷ 100 × {val:g} bu/MT = ({_n(cbot)} + {_n(prem)}) ÷ 100 × {val:g}"
    elif kind == "bu_per_mt":
        txt = f"CIF = CBOT ÷ 100 × {val:g} bu/MT + premium = {_n(cbot)} ÷ 100 × {val:g} + {_n(prem)}"
    elif kind == "st_per_mt" and cents_prem:
        txt = f"CIF = (CBOT + premium) × {val:g} = ({_n(cbot)} + {_n(prem)}) × {val:g}"
    elif kind == "st_per_mt":
        txt = f"CIF = CBOT × {val:g} + premium = {_n(cbot)} × {val:g} + {_n(prem)}"
    else:
        txt = f"CIF = CBOT + premium = {_n(cbot)} + {_n(prem)}"
    return [("f", f"{txt} = {_n(import_usd_mt)} USD/MT")]


def _date(x: Any) -> dt.date | None:
    if isinstance(x, dt.date):
        return x
    try:
        return dt.date.fromisoformat(str(x or "")[:10])
    except ValueError:
        return None


def fifo_stock_days(*, qty: float, rate: float, today: Any, start: Any = None,
                    ahead_mt: float = 0.0, own_remaining: float | None = None) -> dict[str, Any] | None:
    """Days a tonne of this cargo sits in stock, from its place in the FIFO queue.

    ``ahead_mt`` is the stock that will be used before this cargo.  When the
    cargo is already in stock pass ``own_remaining`` (its tonnes left): the
    last tonne is used after ``(ahead + remaining) ÷ rate`` days from today.
    Otherwise the cargo arrives on ``start`` (today if unknown) and waits for
    whatever is still ahead of it then.  The consumption rate is assumed flat.
    """
    today = _date(today) or dt.date.today()
    if not qty or not rate or rate <= 0:
        return None
    use_days = qty / rate
    begin = _date(start)
    known = begin is not None
    if own_remaining is not None:
        last = (ahead_mt + own_remaining) / rate              # days from today
        first = last - use_days
        begin = begin or today
        base = (today - begin).days                           # days already in stock
        first_d, last_d = base + first, base + last           # days from storage start
        if first_d < 0:                                       # cannot start before it landed
            first_d, last_d = 0.0, max(last_d, 0.0)
    else:
        arrive = max(begin or today, today)
        left_ahead = max(0.0, ahead_mt - rate * (arrive - today).days)
        begin = begin or arrive
        first_d = (arrive - begin).days + left_ahead / rate
        last_d = first_d + use_days
    return {"start": begin.isoformat(), "arrival_known": known, "ahead_mt": ahead_mt, "own_remaining": own_remaining,
            "use_days": use_days, "wait_days": first_d, "last_days": last_d,
            "first_use": (begin + dt.timedelta(days=round(first_d))).isoformat(),
            "last_use": (begin + dt.timedelta(days=round(last_d))).isoformat(),
            "avg_days": (first_d + last_d) / 2.0}


def break_even_days(cif_usd: float, fx: float, rate_pct: float, fees_egp: float, local: float) -> float | None:
    """Finance days at which the saving reaches zero.

    saving(d) = local − (CIF × (1 + r·d/360) × FX + fees), so
    d* = (local − fees − CIF×FX) ÷ (CIF × FX × r/360).
    """
    per_day = cif_usd * fx * rate_pct / 100.0 / DAY_BASIS
    if per_day <= 0:
        return None
    return (local - fees_egp - cif_usd * fx) / per_day


def build_workings(inp: Mapping[str, Any], out: Mapping[str, Any], *,
                   fees: list[tuple[str, float]] | None = None,
                   coverage: Mapping[str, Any] | None = None) -> list[tuple[str, str]]:
    """Return the numbered workings for one Deal Evaluator calculation.

    ``fees`` lists the EGP/MT costs added after FX, as (label, value).  In
    contract mode it is the canonical stack (intake + clearance + freight);
    in manual mode pass the chosen intake plus clearance and inland freight.
    ``coverage`` carries the inventory figures: cons_mt_day, coverage_days,
    avg_holding_days, start, end, avg_local, local_carry_mt, local_rate_pct.
    """
    L: list[tuple[str, str]] = []
    comm_meta = inp.get("comm_meta") or {}
    cif = to_float(out.get("import_usd_mt"), None)
    if cif is None:
        return [("n", out.get("error") or "Not enough inputs to show the workings.")]
    fx = to_float(out.get("fx"), None) or to_float(inp.get("fx"), None)
    qty = to_float(inp.get("qty_mt"), 0.0) or 0.0
    days = to_float(inp.get("finance_days"), 0.0) or 0.0
    rate = to_float(inp.get("interest_rate"), 0.0) or 0.0
    local = to_float(inp.get("local_egp_mt"), None)
    carry = to_float(out.get("carry_usd_mt"), 0.0) or 0.0
    own_usd = to_float(out.get("own_after_usd_mt"), cif + carry)
    cov = dict(coverage or {})

    # 1 ── CIF
    L.append(("h", "1 · Import price (CIF)"))
    L += cif_step(comm_meta, inp, cif)

    # 2 ── Finance carry (interest)
    L.append(("h", f"2 · Finance carry (interest) — {DAY_BASIS}-day year"))
    L.append(("n", f"Interest rate {_n(rate)}% a year · finance days {_n(days, 0)} "
                   "(days between paying the supplier and the money coming back)"))
    if 0 < rate <= 1:
        L.append(("n", f"⚠ The rate is read as {_n(rate)}% (not {_n(rate * 100)}%). "
                       f"Type {_n(rate * 100, 0)} for {_n(rate * 100, 0)}%."))
    per_day_usd = cif * rate / 100.0 / DAY_BASIS
    L.append(("f", f"Interest per MT per day = CIF × rate ÷ {DAY_BASIS} = {_n(cif)} × {_n(rate)}% ÷ {DAY_BASIS} "
                   f"= {_n(per_day_usd, 4)} USD/MT/day"))
    L.append(("f", f"Finance carry = CIF × rate × days ÷ {DAY_BASIS} = {_n(cif)} × {_n(rate)}% × {_n(days, 0)} ÷ {DAY_BASIS} "
                   f"= {_n(carry)} USD/MT"))
    if cif:
        L.append(("f", f"   = {_n(carry / cif * 100, 3)}% of the CIF price"))
    if fx:
        L.append(("f", f"Carry in EGP = {_n(carry)} × FX {_n(fx, 4)} = {_n(carry * fx)} EGP/MT"))
        if qty:
            L.append(("k", f"Carry on the cargo = {_n(carry * fx)} × {_n(qty, 0)} MT = {_n(carry * fx * qty, 0)} EGP "
                           f"({_n(carry * qty, 0)} USD)"))
            L.append(("k", f"Each extra day financed costs {_n(per_day_usd * fx, 2)} EGP/MT "
                           f"= {_n(per_day_usd * fx * qty, 0)} EGP a day on {_n(qty, 0)} MT"))
    if days <= 0 or rate <= 0:
        L.append(("n", "No finance carry: enter Finance Days and Interest Rate to include it "
                       "(Home / Portfolio show the cost without carry)."))

    # 3 ── Own cost
    L.append(("h", "3 · Own cost after carry"))
    L.append(("f", f"Own after USD = CIF + carry = {_n(cif)} + {_n(carry)} = {_n(own_usd)} USD/MT"))
    own_egp = None
    if fx:
        own_egp = own_usd * fx
        L.append(("f", f"Own after EGP = {_n(own_usd)} × FX {_n(fx, 4)} = {_n(own_egp)} EGP/MT"))
    fee_total = sum(to_float(v, 0.0) or 0.0 for _, v in (fees or []))
    landed = None
    if own_egp is not None:
        if fees:
            parts = " + ".join(f"{lbl} {_n(v)}" for lbl, v in fees)
            L.append(("f", f"Fees after FX = {parts} = {_n(fee_total)} EGP/MT"))
        landed = own_egp + fee_total
        L.append(("k", f"Landed cost = {_n(own_egp)} + {_n(fee_total)} = {_n(landed)} EGP/MT"))

    # 4 ── Saving
    if local is not None and landed is not None:
        L.append(("h", "4 · Saving against the local price"))
        saving = local - landed
        L.append(("x" if saving < 0 else "k", f"Saving = local − landed = {_n(local)} − {_n(landed)} = {_signed(saving)} EGP/MT"
                       + ("  (a loss)" if saving < 0 else "")))
        if qty:
            L.append(("f", f"On the cargo = {_signed(saving)} × {_n(qty, 0)} MT = {_signed(saving * qty, 0)} EGP"))
        ind = to_float(out.get("indirect_saving_egp_mt"), None)
        if inp.get("canonical_landed_fees_egp_mt") is None and ind is not None and abs(ind - saving) > 0.005:
            L.append(("n", f"With indirect intake instead the saving is {_signed(ind)} EGP/MT."))
        if carry and fx:
            L.append(("n", f"Without the finance carry the saving would be {_signed(saving + carry * fx)} EGP/MT; "
                           f"interest takes {_n(carry * fx)} EGP/MT of it."))
        be = break_even_days(cif, fx, rate, fee_total, local)
        if be is None:
            L.append(("n", "Break-even finance days: not applicable (no interest rate)."))
        elif be < 0:
            L.append(("x", "Break-even finance days: none — the deal loses money even with 0 finance days."))
        else:
            L.append(("f", f"Break-even finance days = (local − fees − CIF×FX) ÷ (CIF × FX × rate ÷ {DAY_BASIS})"))
            L.append(("f", f"   = ({_n(local)} − {_n(fee_total)} − {_n(cif * fx)}) ÷ {_n(per_day_usd * fx, 4)} "
                           f"= {_n(be, 0)} days"))
            L.append(("k" if be >= days else "x", f"The import stays cheaper than local while it is financed for less than {_n(be, 0)} days "
                           f"({_n(be - days, 0)} days of headroom over the {_n(days, 0)} entered)."
                           if be >= days else
                           f"Financed for {_n(days, 0)} days the import costs more than local; it needs "
                           f"{_n(be, 0)} days or fewer."))

    # 5 ── Inventory days
    L.append(("h", "5 · Days in inventory (what finance days should cover)"))
    cons = to_float(cov.get("cons_mt_day"), None)
    cover = to_float(cov.get("coverage_days"), None)
    hold = to_float(cov.get("avg_holding_days"), None)
    if cons and cons > 0:
        key = cov.get("cons_key")
        L.append(("f", f"Consumption = {_n(cons)} MT/day" + (f" (rate saved for {key})" if key else "")))
        cover = cover if cover is not None else qty / cons
        L.append(("f", f"Days to use the cargo = qty ÷ consumption = {_n(qty, 0)} ÷ {_n(cons)} = {_n(cover)} days"))
        hold = hold if hold is not None else cover / 2.0
        L.append(("f", f"Average days a tonne is in stock = {_n(cover)} ÷ 2 = {_n(hold)} days"))
        L.append(("n", "The first tonne is used on arrival and the last after the full period, "
                       "so on average each tonne sits half of it in stock."))
        if cov.get("start"):
            L.append(("f", f"Storage start {cov['start']} → estimated finish {cov.get('end') or '-'}"))
        fifo = cov.get("fifo")
        if fifo:
            L.append(("n", "That assumes the cargo is used from the day it lands. On the FIFO queue it waits "
                           "behind older stock:"))
            if fifo.get("own_remaining") is not None:
                L.append(("f", f"In stock today: {_n(fifo['ahead_mt'], 0)} MT ahead of it + {_n(fifo['own_remaining'], 0)} MT "
                               f"of it left ÷ {_n(cons)} = last tonne used in "
                               f"{_n((fifo['ahead_mt'] + fifo['own_remaining']) / cons)} days (≈ {fifo['last_use']})"))
            else:
                L.append(("f", f"Stock ahead of it: {_n(fifo['ahead_mt'], 0)} MT"
                               + (f" today; arrives {fifo['start']}" if fifo.get("arrival_known")
                                  else " today (no arrival date, so it is treated as arriving today)")))
            L.append(("f", f"Waits {_n(fifo['wait_days'])} days, then used over {_n(fifo['use_days'])} days "
                           f"(≈ {fifo['first_use']} → {fifo['last_use']})"))
            L.append(("k", f"Average days a tonne sits in stock (FIFO) = {_n(fifo['wait_days'])} + "
                           f"{_n(fifo['use_days'])} ÷ 2 = {_n(fifo['avg_days'])} days from {fifo['start']}"))
            hold = to_float(fifo.get("avg_days"), hold)
        hold_carry = cif * rate / 100.0 * hold / DAY_BASIS
        L.append(("f", f"Carry for {_n(hold)} stock days = {_n(cif)} × {_n(rate)}% × {_n(hold)} ÷ {DAY_BASIS} "
                       f"= {_n(hold_carry)} USD/MT"
                       + (f" = {_n(hold_carry * fx)} EGP/MT" if fx else "")))
        if fx and abs(hold - days) >= 0.5:
            diff = (hold_carry - carry) * fx
            L.append(("k", f"Finance days entered ({_n(days, 0)}) vs average days in stock ({_n(hold, 0)}): "
                           f"using the stock days would change the cost by {_signed(diff)} EGP/MT "
                           f"({_signed(diff * qty, 0)} EGP on the cargo)."))
        L.append(("n", "If the supplier is paid before arrival, add the days between payment and arrival "
                       "to the stock days."))
        avg_local = to_float(cov.get("avg_local"), None)
        lc = to_float(cov.get("local_carry_mt"), None)
        lr = to_float(cov.get("local_rate_pct"), rate)
        if avg_local is not None and lc is not None:
            L.append(("f", f"Local carry = average local price × rate × stock days ÷ {DAY_BASIS} = "
                           f"{_n(avg_local, 0)} × {_n(lr)}% × {_n(cov.get('avg_holding_days'))} ÷ {DAY_BASIS} = {_n(lc)} EGP/MT"
                           + (f" = {_n(lc * qty, 0)} EGP" if qty else "")))
            L.append(("n", "That is the interest on the stock valued at the local price, on the simple average days (as in Coverage & carry detail)."))
    else:
        L.append(("n", "No consumption rate is set for this commodity (Settings → Consumption), "
                       "so the days in inventory cannot be worked out."))
    return L


def as_text(lines: list[tuple[str, str]]) -> str:
    """Plain-text rendering, used for copying the workings."""
    out = []
    for kind, txt in lines:
        if kind == "h":
            out.append(("\n" if out else "") + txt)
        else:
            out.append(("  • " if kind == "n" else "  ") + txt)
    return "\n".join(out)

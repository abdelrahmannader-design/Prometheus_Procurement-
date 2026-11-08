"""Stress test on the open contracts, valued like the Home Open MTM.

Each open contract arrives as a *position* (built by the app from the same
valuation as Home: live CBOT + premium for unpriced contracts, Form 4 FX when
recorded, route freight, today's origin-matched local price). A scenario moves
three things, and each only where the contract is really exposed:

* CBOT  — only the unpriced share of a contract whose CIF is still live
          (CBOT + premium); fixed / saved CIFs do not move.
* FX    — only contracts without Form 4 (their dollars are not bought yet).
* Local — the local market price excl. transport, for every contract; the
          transport on the local quote stays as it is.

The change per tonne is split exactly into from-CBOT, from-FX and from-local.
Break-evens say how far each driver can move before the contract stops beating
local. Both transport bases are supported: incl. (import with inland freight vs
local + its transport) and excl. (without either).
"""
from __future__ import annotations

import itertools

DEFAULT_CBOT = (-0.05, 0.0, 0.05, 0.10)
DEFAULT_FX = (-0.03, 0.0, 0.03, 0.05, 0.10)
DEFAULT_LOCAL = (-0.05, -0.03, 0.0, 0.03, 0.05)


def _n(v):
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def exposure(p):
    """(unpriced share moving with CBOT, FX moves?) for one position."""
    qty = _n(p.get("qty")) or 0.0
    live = (p.get("cif_basis") == "live") and _n(p.get("cbot")) is not None and _n(p.get("factor"))
    u = 0.0
    if live and qty > 0:
        u = min(max((_n(p.get("unpriced_mt")) or 0.0) / qty, 0.0), 1.0)
    return u, not bool(p.get("fx_secured"))


def revalue(p, dc=0.0, dfx=0.0, dloc=0.0, excl=False):
    """One position under a shock (fractions: dc CBOT, dfx FX, dloc local price).

    Returns base and shocked own-after / local / saving per MT and in total,
    the exact split of the change and a verdict. ``ok`` is False when the
    position lacks CIF, FX or a local price (left out of totals, never zero).
    """
    qty = _n(p.get("qty")) or 0.0
    cif, fx = _n(p.get("cif")), _n(p.get("fx"))
    local, lt = _n(p.get("local")), _n(p.get("local_transport"))
    fees_x = (_n(p.get("disc")) or 0.0) + (_n(p.get("clr")) or 0.0)
    freight = 0.0 if excl else (_n(p.get("freight")) or 0.0)
    out = {"id": p.get("id"), "qty": qty, "ok": False}
    if cif is None or not fx or local is None or (excl and lt is None):
        out["why"] = ("no CIF" if cif is None else "no FX" if not fx else
                      "no local price" if local is None else "no local transport on the quote")
        return out
    u, fx_moves = exposure(p)
    cbot, factor = _n(p.get("cbot")) or 0.0, _n(p.get("factor")) or 0.0
    dcif = u * cbot * dc * factor                       # USD/MT
    fx1 = fx * (1.0 + dfx) if fx_moves else fx
    lx0 = local - (lt or 0.0)                           # market price excl. transport
    lx1 = lx0 * (1.0 + dloc)
    l0 = lx0 if excl else local
    l1 = lx1 if excl else lx1 + (lt or 0.0)
    own0 = cif * fx + fees_x + freight
    own1 = (cif + dcif) * fx1 + fees_x + freight
    s0, s1 = l0 - own0, l1 - own1
    f_cbot = -dcif * fx
    f_fx = -(cif + dcif) * (fx1 - fx)
    f_loc = l1 - l0
    verdict = ("holds" if s0 >= 0 and s1 >= 0 else "flips to loss" if s0 >= 0 > s1
               else "turns to saving" if s1 >= 0 > s0 else "stays a loss")
    out.update(ok=True, own0=own0, own1=own1, local0=l0, local1=l1, sav0=s0, sav1=s1,
               tot0=s0 * qty, tot1=s1 * qty, chg=(s1 - s0) * qty,
               from_cbot=f_cbot * qty, from_fx=f_fx * qty, from_local=f_loc * qty,
               cbot_mt=u * qty, fx_mt=qty if fx_moves else 0.0, verdict=verdict)
    out.update(break_even(p, excl))
    return out


def break_even(p, excl=False):
    """How far CBOT, FX or the local price can move before the saving is zero."""
    qty = _n(p.get("qty")) or 0.0
    cif, fx = _n(p.get("cif")), _n(p.get("fx"))
    local, lt = _n(p.get("local")), _n(p.get("local_transport"))
    if cif is None or not fx or local is None:
        return {}
    fees = (_n(p.get("disc")) or 0.0) + (_n(p.get("clr")) or 0.0) + (0.0 if excl else (_n(p.get("freight")) or 0.0))
    lx0 = local - (lt or 0.0)
    L = lx0 if excl else local
    s0 = L - (cif * fx + fees)
    u, fx_moves = exposure(p)
    cbot, factor = _n(p.get("cbot")), _n(p.get("factor"))
    out = {"be_cbot": None, "be_cbot_move": None, "be_fx": None, "be_fx_move": None,
           "be_local_move": (-s0 / lx0) if lx0 else None}
    if u > 0 and cbot and factor:
        lvl = cbot + s0 / (u * factor * fx)
        out.update(be_cbot=lvl, be_cbot_move=lvl / cbot - 1.0)
    if fx_moves and cif:
        lvl = (L - fees) / cif
        out.update(be_fx=lvl, be_fx_move=lvl / fx - 1.0)
    return out


def scenario_total(positions, dc=0.0, dfx=0.0, dloc=0.0, excl=False, dc_by_base=None):
    """Totals of one scenario. ``dc_by_base`` overrides the CBOT shock per commodity."""
    t = {"tot0": 0.0, "tot1": 0.0, "chg": 0.0, "from_cbot": 0.0, "from_fx": 0.0, "from_local": 0.0,
         "qty": 0.0, "n": 0, "na": 0, "loss_n": 0, "loss_mt": 0.0, "flips": 0, "cbot_mt": 0.0, "fx_mt": 0.0}
    rows = []
    for p in positions:
        d = (dc_by_base or {}).get(p.get("base"), dc) if dc_by_base is not None else dc
        r = revalue(p, d, dfx, dloc, excl)
        rows.append(r)
        if not r["ok"]:
            t["na"] += 1
            continue
        t["n"] += 1
        for k in ("tot0", "tot1", "chg", "from_cbot", "from_fx", "from_local", "qty", "cbot_mt", "fx_mt"):
            t[k] += r[k]
        if r["sav1"] < 0:
            t["loss_n"] += 1
            t["loss_mt"] += r["qty"]
        if r["verdict"] == "flips to loss":
            t["flips"] += 1
    t["rows"] = rows
    return t


def clean(shocks, default):
    vals = sorted({round(float(x), 6) for x in (shocks or default) if _n(x) is not None and float(x) > -1.0} | {0.0})
    return tuple(vals)


def run(positions, cbot=None, fx=None, local=None, excl=False, history=None):
    """The full test: base, best, adverse, an optional history case, and the
    CBOT × FX grid for every local shock.

    ``history`` = {base commodity: CBOT shock} (e.g. the worst 30-day rise seen).
    """
    cbot, fx, local = clean(cbot, DEFAULT_CBOT), clean(fx, DEFAULT_FX), clean(local, DEFAULT_LOCAL)
    named = [("Base", 0.0, 0.0, 0.0, None),
             ("Best", min(cbot), min(fx), max(local), None),
             ("Adverse", max(cbot), max(fx), min(local), None)]
    if history:
        named.append(("History", None, max(fx), min(local), dict(history)))
    scen = []
    for name, dc, dfx, dloc, by in named:
        t = scenario_total(positions, dc or 0.0, dfx, dloc, excl, by)
        t.update(name=name, dc=dc, dfx=dfx, dloc=dloc, dc_by_base=by)
        scen.append(t)
    grid = {}
    for dloc in local:
        for dc, dfx in itertools.product(cbot, fx):
            t = scenario_total(positions, dc, dfx, dloc, excl)
            grid[(dc, dfx, dloc)] = {k: t[k] for k in ("tot1", "chg", "loss_n", "loss_mt", "flips")}
    worst = min(grid.items(), key=lambda kv: kv[1]["tot1"]) if grid else None
    return {"excl": excl, "cbot": cbot, "fx": fx, "local": local, "scenarios": scen, "grid": grid,
            "worst": {"dc": worst[0][0], "dfx": worst[0][1], "dloc": worst[0][2], **worst[1]} if worst else None,
            "positions": len(positions),
            "cbot_exposed_mt": sum(exposure(p)[0] * (_n(p.get("qty")) or 0.0) for p in positions),
            "fx_exposed_mt": sum((_n(p.get("qty")) or 0.0) for p in positions if exposure(p)[1])}


def pct(x, signed=True):
    return "—" if x is None else (f"{x * 100:+.1f}%" if signed else f"{x * 100:.1f}%")


def describe(t, excl=False):
    """'CBOT +10% · FX +10% · local −5%' for a scenario total."""
    if t.get("dc_by_base"):
        cb = "CBOT " + ", ".join(f"{b} {pct(v)}" for b, v in sorted(t["dc_by_base"].items()))
    else:
        cb = f"CBOT {pct(t.get('dc') or 0.0)}"
    return f"{cb} · FX {pct(t.get('dfx') or 0.0)} · local {pct(t.get('dloc') or 0.0)}" + (" · excl. transport" if excl else "")


def summary(res, money=lambda v: f"EGP {v:,.0f}"):
    """Plain-language lines for the test."""
    sc = {s["name"]: s for s in res["scenarios"]}
    b, a = sc["Base"], sc["Adverse"]
    basis = "excl. transport" if res["excl"] else "incl. transport"
    lines = [f"Open book today: {money(b['tot0'])} vs local ({basis}) on {b['qty']:,.0f} MT "
             f"— {res['cbot_exposed_mt']:,.0f} MT still move with CBOT, {res['fx_exposed_mt']:,.0f} MT have no Form 4."]
    lines.append(f"Adverse ({describe(a)}): {money(a['tot1'])} ({money(a['chg'])}) — CBOT {money(a['from_cbot'])}, "
                 f"FX {money(a['from_fx'])}, local {money(a['from_local'])}; {a['loss_n']} contract(s) below local "
                 f"({a['loss_mt']:,.0f} MT), {a['flips']} flip from saving to loss.")
    if "History" in sc:
        h = sc["History"]
        lines.append(f"History case ({describe(h)}): {money(h['tot1'])} ({money(h['chg'])}); {h['loss_n']} contract(s) below local.")
    w = res.get("worst")
    if w:
        lines.append(f"Worst point of the grid: CBOT {pct(w['dc'])}, FX {pct(w['dfx'])}, local {pct(w['dloc'])} → {money(w['tot1'])}.")
    if b["na"]:
        lines.append(f"{b['na']} contract(s) not assessable (missing CIF, FX or local price) — left out, not counted as zero.")
    return lines

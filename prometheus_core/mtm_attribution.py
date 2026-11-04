"""Why an open contract's saving per tonne moved between two daily snapshots.

saving/MT = local − own cost, own cost = CIF $/MT × FX + discharge + clearance + freight (+ other fees).
The change is split in a fixed order so the parts add up exactly to the change in saving/MT:

  from CBOT / CIF  = −(CIF today − CIF prior) × FX prior    (an unpriced contract's CIF moves with CBOT)
  from FX          = −CIF today × (FX today − FX prior)       (0 when Form 4 has fixed the FX)
  from local       = local today − local prior
  other            = the rest: discharge, clearance, freight or any other fee that changed
"""
from __future__ import annotations


def _n(v):
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def attribute(today, prior):
    """Parts of the change in saving/MT between two snapshot rows; None where a value is missing."""
    t, p = today or {}, prior or {}
    c1, c0 = _n(t.get("cif_usd_mt")), _n(p.get("cif_usd_mt"))
    f1, f0 = _n(t.get("fx")), _n(p.get("fx"))
    l1, l0 = _n(t.get("local_egp_mt")), _n(p.get("local_egp_mt"))
    s1, s0 = _n(t.get("saving_egp_mt")), _n(p.get("saving_egp_mt"))
    out = {"from_cbot": None, "from_fx": None, "from_local": None, "other": None,
           "change": (s1 - s0) if None not in (s1, s0) else None}
    if None not in (c1, c0, f0):
        out["from_cbot"] = -(c1 - c0) * f0
    if None not in (c1, f1, f0):
        out["from_fx"] = -c1 * (f1 - f0)
    if None not in (l1, l0):
        out["from_local"] = l1 - l0
    parts = [out["from_cbot"], out["from_fx"], out["from_local"]]
    if out["change"] is not None and None not in parts:
        out["other"] = out["change"] - sum(parts)
    return out


def explain(a, threshold=0.5):
    """Short text such as 'CBOT +88 · FX 0 · local −100' for a tooltip or summary."""
    names = (("from_cbot", "CBOT"), ("from_fx", "FX"), ("from_local", "local"), ("other", "other"))
    bits = [f"{lab} {a[k]:+,.0f}" if abs(a[k]) >= threshold else f"{lab} 0" for k, lab in names if a.get(k) is not None]
    return " · ".join(bits)

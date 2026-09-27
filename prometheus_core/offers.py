"""Compare supplier offers on true landed cost.

Every offer is priced on the same market (CBOT, FX, interest rate) so the
ranking reflects only what differs between offers: premium or flat price,
freight, intake, clearance, payment terms (finance days) and quality.

    CIF USD/MT     = (CBOT + premium) × factor          (CBOT offer)
                   = flat CIF                          (flat offer)
    Carry USD/MT   = CIF × rate% × payment days / 360
    Landed EGP/MT  = (CIF + carry) × FX + freight + intake + clearance + quality adj.
    Saving vs local = local − landed   (positive = import cheaper)
"""

from __future__ import annotations

from typing import Any

from .cbot import cbot_conv_factor
from .numbers import to_float

OFFERS_ENGINE_VERSION = "1.0"


def _carry_mult(rate_pct: float, days: float) -> float:
    return 1.0 + (rate_pct / 100.0) * (days / 360.0)


def compare_offers(shared: dict[str, Any], offers: list[dict[str, Any]]) -> dict[str, Any]:
    commodity = str(shared.get("commodity") or "").upper()
    factor = to_float(shared.get("factor"), None) or cbot_conv_factor(commodity, strict=True)
    cbot = to_float(shared.get("cbot"), None)
    fx = to_float(shared.get("fx"), None)
    rate = to_float(shared.get("interest_rate_pct"), 0.0) or 0.0
    local = to_float(shared.get("local_egp_mt"), None)

    rows: list[dict[str, Any]] = []
    for i, o in enumerate(offers or [], start=1):
        name = (str(o.get("name") or "").strip() or f"Offer {i}")
        kind = str(o.get("price_type") or "CBOT").upper()
        prem = to_float(o.get("premium"), None)
        flat = to_float(o.get("flat_cif"), None)
        days = to_float(o.get("payment_days"), 0.0) or 0.0
        # Intake: Direct and Indirect are alternative routes — only the
        # selected one is charged.  A plain intake_egp_mt is still accepted.
        mode = str(o.get("intake_mode") or "DIRECT").upper()
        direct = to_float(o.get("intake_direct_egp_mt"), None)
        indirect = to_float(o.get("intake_indirect_egp_mt"), None)
        if direct is not None or indirect is not None:
            intake = (indirect if mode.startswith("INDIRECT") else direct) or 0.0
        else:
            intake = to_float(o.get("intake_egp_mt"), 0.0) or 0.0
        fees = intake + sum(to_float(o.get(k), 0.0) or 0.0
                            for k in ("freight_egp_mt", "clearance_egp_mt"))
        quality = to_float(o.get("quality_adj_egp_mt"), 0.0) or 0.0
        qty = to_float(o.get("qty_mt"), None)
        missing = []
        cif = None
        if kind == "FLAT":
            if flat is None:
                missing.append("flat CIF")
            cif = flat
        else:
            if prem is None:
                missing.append("premium")
            if cbot is None:
                missing.append("CBOT")
            if not factor:
                missing.append("conversion factor (use Flat CIF for this commodity)")
            if not missing:
                cif = (cbot + prem) * factor
        if fx is None:
            missing.append("FX")
        mult = _carry_mult(rate, days)
        carry = cif * (mult - 1.0) if cif is not None else None
        landed = ((cif * mult) * fx + fees + quality) if (cif is not None and fx) else None
        saving = (local - landed) if (local is not None and landed is not None) else None
        rows.append({
            "index": i, "name": name, "supplier": o.get("supplier", ""), "origin": o.get("origin", ""),
            "price_type": kind, "premium": prem, "flat_cif": flat, "payment_days": days,
            "fees_egp_mt": fees, "intake_egp_mt": intake, "intake_mode": "INDIRECT" if mode.startswith("INDIRECT") else "DIRECT",
            "quality_adj_egp_mt": quality, "qty_mt": qty,
            "cif_usd_mt": cif, "carry_usd_mt": carry, "carry_mult": mult,
            "landed_egp_mt": landed, "saving_vs_local_egp_mt": saving,
            "saving_total_egp": (saving * qty) if (saving is not None and qty) else None,
            "missing": missing,
        })

    valid = [r for r in rows if r["landed_egp_mt"] is not None]
    valid.sort(key=lambda r: r["landed_egp_mt"])
    best = valid[0] if valid else None
    for rank, r in enumerate(valid, start=1):
        r["rank"] = rank
    for r in rows:
        r.setdefault("rank", None)
        r["gap_vs_best_egp_mt"] = (r["landed_egp_mt"] - best["landed_egp_mt"]
                                   if (best and r["landed_egp_mt"] is not None) else None)
        r["gap_vs_best_total_egp"] = (r["gap_vs_best_egp_mt"] * r["qty_mt"]
                                      if (r["gap_vs_best_egp_mt"] is not None and r["qty_mt"]) else None)
        fixed = r["fees_egp_mt"] + r["quality_adj_egp_mt"]
        # Price that would make this offer exactly as cheap as the best one,
        # and the highest price that still beats buying locally.
        r["match_best_price"] = r["max_price_vs_local"] = None
        if fx and r["carry_mult"]:
            def _to_price(target_landed: float):
                usd = (target_landed - fixed) / fx / r["carry_mult"]
                if r["price_type"] == "FLAT":
                    return usd
                if factor and cbot is not None:
                    return usd / factor - cbot
                return None
            if best is not None:
                r["match_best_price"] = _to_price(best["landed_egp_mt"])
            if local is not None:
                r["max_price_vs_local"] = _to_price(local)

    return {
        "rows": sorted(rows, key=lambda r: (r["rank"] is None, r["rank"] or 0, r["index"])),
        "best": best,
        "factor": factor, "cbot": cbot, "fx": fx, "interest_rate_pct": rate,
        "local_egp_mt": local, "commodity": commodity,
        "version": OFFERS_ENGINE_VERSION,
    }

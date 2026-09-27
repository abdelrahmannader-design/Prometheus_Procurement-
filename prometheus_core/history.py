"""Change history and approvals.

History: every save compares the key records (contracts, local purchases,
local prices, budgets) with how they were at the previous save and logs one
line per changed field — who, when, which record, old → new.

Approvals: a request freezes a fingerprint of the record's key terms; if
the record is edited afterwards the approval shows "changed after approval".
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

HISTORY_ENGINE_VERSION = "1.0"

IGNORE_FIELDS = {"ts", "updated", "created_ts", "provenance", "recorded_at", "last_calc", "last_calc_ts",
                 "saved_ts", "refs_source"}

APPROVAL_FIELDS = {
    "contract": ("supplier", "commodity", "origin", "qty_mt", "cif_usd_mt", "premium_cents", "futures_month",
                 "delivery_date", "delivery_fx", "discharge_egp_mt", "clearance_egp_mt", "freight_egp_mt"),
    "local_purchase": ("date", "commodity", "supplier", "qty_mt", "price_egp_mt", "transport_egp_mt"),
}


def _canon(v: Any) -> str:
    try:
        return json.dumps(v, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(v)


def snapshot(state: dict[str, Any]) -> dict[str, dict[str, dict[str, str]]]:
    """{entity: {key: {field: canonical value}}} of the records we track."""
    out: dict[str, dict[str, dict[str, str]]] = {"contract": {}, "local_purchase": {}, "local_price": {},
                                                 "budget": {}}

    def fields(rec):
        return {k: _canon(v) for k, v in (rec or {}).items()
                if k not in IGNORE_FIELDS and not str(k).startswith("_")}

    for cid, c in (state.get("contracts") or {}).items():
        if isinstance(c, dict):
            out["contract"][str(cid)] = fields(c)
    for r in state.get("local_purchases") or []:
        if isinstance(r, dict):
            key = str(r.get("id") if r.get("id") is not None else f"{r.get('date')}|{r.get('commodity')}")
            out["local_purchase"][key] = fields(r)
    for r in state.get("local_prices") or []:
        if isinstance(r, dict):
            out["local_price"][f"{r.get('date')}|{str(r.get('commodity', '')).upper()}"] = fields(r)
    for b in state.get("budgets") or []:
        if isinstance(b, dict):
            out["budget"][f"{str(b.get('commodity', '')).upper()}|{b.get('year')}"] = fields(b)
    return out


def _show(v: str | None) -> str:
    if v is None:
        return ""
    try:
        x = json.loads(v)
    except (TypeError, ValueError):
        return v[:120]
    if isinstance(x, list):
        return f"[{len(x)} item(s)]"
    if isinstance(x, dict):
        return f"{{{len(x)} field(s)}}"
    if x is None:
        return ""
    return str(x)[:120]


def _same_number(a: str | None, b: str | None) -> bool:
    try:
        return abs(float(json.loads(a)) - float(json.loads(b))) < 1e-9
    except (TypeError, ValueError):
        return False


def diff(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    """Field-level changes between two snapshots."""
    out = []
    for entity in after.keys() | before.keys():
        b, a = before.get(entity, {}), after.get(entity, {})
        for key in sorted(a.keys() - b.keys()):
            out.append({"entity": entity, "key": key, "action": "ADDED", "field": "", "old": "",
                        "new": ""})
        for key in sorted(b.keys() - a.keys()):
            out.append({"entity": entity, "key": key, "action": "DELETED", "field": "", "old": "", "new": ""})
        for key in sorted(a.keys() & b.keys()):
            if a[key] == b[key]:
                continue
            for f in sorted(a[key].keys() | b[key].keys()):
                ov, nv = b[key].get(f), a[key].get(f)
                if ov == nv or _show(ov) == _show(nv) or _same_number(ov, nv):
                    continue
                out.append({"entity": entity, "key": key, "action": "EDITED", "field": f,
                            "old": _show(ov), "new": _show(nv)})
    return out


def fingerprint(entity: str, rec: dict[str, Any] | None) -> str:
    rec = rec or {}
    payload = {f: rec.get(f) for f in APPROVAL_FIELDS.get(entity, ())}
    for k, v in payload.items():
        try:
            payload[k] = round(float(v), 6) if v not in (None, "") and not isinstance(v, bool) else v
        except (TypeError, ValueError):
            payload[k] = str(v).strip().upper()
    return hashlib.sha256(_canon(payload).encode("utf-8")).hexdigest()[:16]


def changed_terms(entity: str, frozen: dict[str, Any], rec: dict[str, Any] | None) -> list[str]:
    """Which key terms differ from the terms frozen at request time."""
    rec = rec or {}
    out = []
    for f in APPROVAL_FIELDS.get(entity, ()):
        a, b = (frozen or {}).get(f), rec.get(f)
        try:
            same = abs(float(a) - float(b)) < 1e-9
        except (TypeError, ValueError):
            same = str(a or "").strip().upper() == str(b or "").strip().upper()
        if not same:
            out.append(f)
    return out


def approval_status(approval: dict[str, Any], rec: dict[str, Any] | None) -> str:
    """PENDING / APPROVED / REJECTED / WITHDRAWN, or CHANGED when the record was
    edited after the request, or MISSING when it was deleted."""
    st = str(approval.get("status") or "PENDING").upper()
    if st in ("REJECTED", "WITHDRAWN"):
        return st
    if rec is None:
        return "MISSING"
    if fingerprint(approval.get("entity", ""), rec) != approval.get("fingerprint"):
        return "CHANGED"
    return st


def hash_pin(pin: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{pin}".encode("utf-8")).hexdigest()

"""Pick contracts from pasted names ("SC-34179-CH.1, 460/20050610 2000, …") and total what is open.

Used by the CBOT export's "Only these contracts" box. A name matches a contract by its id or its exact name
(case, spaces and warning marks ignored); otherwise a single contract whose name differs only by a suffix after
a separator ("460/20050010" ↔ "460/20050010-COPY"). A name that matches nothing, or more than one contract,
is reported, never guessed.
"""

from __future__ import annotations

import re

_SEP = (" ", ".", "-", "_", "/", "(")


def norm(name):
    return re.sub(r"\s+", " ", str(name or "").replace("⚠", "")).strip().upper()


def _extends(longer, shorter):
    return longer != shorter and longer.startswith(shorter) and longer[len(shorter):len(shorter) + 1] in _SEP


def _base(c):
    return str((c or {}).get("commodity") or "").upper().split("-")[0]


def is_open(c):
    return str((c or {}).get("status") or "Open").strip().lower() != "closed"


def is_received(c):
    return bool(str((c or {}).get("storage_start") or (c or {}).get("delivery_date") or "").strip())


def split_names(text):
    return [t.strip() for t in re.split(r"[,;\n]+", text or "") if t.strip()]


def pick_contracts(contracts, base, text):
    """{ids, matched [(name, cid, app name, how)], unmatched [name], ambiguous [(name, [app names])]};
    ids is None when ``text`` is empty (= every contract)."""
    names = split_names(text)
    pool = {cid: c for cid, c in (contracts or {}).items() if isinstance(c, dict) and _base(c) == base}
    out = {"ids": None if not names else set(), "matched": [], "unmatched": [], "ambiguous": []}
    for name in names:
        key = norm(name)
        hits = [cid for cid in pool if norm(cid) == key] or [cid for cid, c in pool.items() if norm(c.get("name")) == key]
        how = "exact"
        if not hits:
            hits = [cid for cid, c in pool.items() if _extends(norm(c.get("name")), key) or _extends(key, norm(c.get("name")))]
            how = "suffix"
        if len(hits) == 1:
            out["ids"].add(hits[0])
            out["matched"].append((name, hits[0], pool[hits[0]].get("name") or hits[0], how))
        elif not hits:
            out["unmatched"].append(name)
        else:
            out["ambiguous"].append((name, sorted(pool[h].get("name") or h for h in hits)))
    return out


def open_totals(contracts, base, ids=None):
    """Open / closed tonnes among ``ids`` (None = every ``base`` contract), and the open contracts left out."""
    pool = {cid: c for cid, c in (contracts or {}).items() if isinstance(c, dict) and _base(c) == base}
    sel = set(pool) if ids is None else {i for i in ids if i in pool}
    mt = lambda cid: float(pool[cid].get("qty_mt") or 0.0)
    op = [cid for cid in sel if is_open(pool[cid])]
    rec = [cid for cid in op if is_received(pool[cid])]
    left_out = sorted((cid for cid in pool if cid not in sel and is_open(pool[cid])),
                      key=lambda cid: str(pool[cid].get("name") or cid))
    return {"open_n": len(op), "open_mt": sum(mt(c) for c in op), "received_mt": sum(mt(c) for c in rec),
            "not_received_mt": sum(mt(c) for c in op if c not in rec),
            "closed_n": len(sel) - len(op), "closed_mt": sum(mt(c) for c in sel if c not in op),
            "left_out": [(pool[c].get("name") or c, mt(c)) for c in left_out]}


def describe(pick, totals):
    """One or two lines for the dialog."""
    if pick["ids"] is None:
        head = "All contracts"
    else:
        head = f"{len(pick['matched'])} of {len(pick['matched']) + len(pick['unmatched']) + len(pick['ambiguous'])} matched"
    t = totals
    s = (f"{head} · open {t['open_n']} contract(s) {t['open_mt']:,.0f} MT (received {t['received_mt']:,.0f}, "
         f"not received {t['not_received_mt']:,.0f}) · closed {t['closed_n']} ({t['closed_mt']:,.0f} MT)")
    extra = []
    if pick["unmatched"]:
        extra.append("not found: " + ", ".join(pick["unmatched"]))
    if pick["ambiguous"]:
        extra.append("more than one contract: " + "; ".join(f"{n} → {' / '.join(a)}" for n, a in pick["ambiguous"]))
    renamed = [f"{n} → {a}" for n, _cid, a, how in pick["matched"] if how == "suffix"]
    if renamed:
        extra.append("matched by number: " + ", ".join(renamed))
    if pick["ids"] is not None and t["left_out"]:
        extra.append("open but not in your list: " + ", ".join(f"{n} ({m:,.0f} MT)" for n, m in t["left_out"]))
    return s + ("\n" + "\n".join(extra) if extra else "")

"""Freight rate history: every rate change of a route kept with its effective date.

A route record holds ``history`` = [{effective, rate, recorded_at}] (new records), or —
for records saved before history was kept — one previous rate (``old_rate``, in force
before ``effective``) and the current ``rate``. A delivery is charged the rate in
force on its date, so a later increase never changes past costs.
"""
from __future__ import annotations

import datetime as dt


def _num(v):
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def freight_segments(rec):
    """A freight route's rates as [(effective date, rate)], oldest first.

    New records keep every change in ``history``; older ones have one previous
    rate (``old_rate``, in force before ``effective``) and the current ``rate``.
    """
    rec = rec or {}
    hist = rec.get("history")
    if isinstance(hist, list) and hist:
        segs = [(str(h.get("effective") or "")[:10], _num(h.get("rate"))) for h in hist if isinstance(h, dict)]
        return sorted([x for x in segs if x[1] is not None], key=lambda x: x[0])
    old, new = _num(rec.get("old_rate")), _num(rec.get("rate"))
    eff = str(rec.get("effective") or "")[:10]
    segs = [("", old)] if old is not None else []
    if new is not None:
        segs.append((eff if old is not None else "", new))
    return segs


def freight_rate_on(rec, day):
    """The rate in force on ``day``: (rate, effective date, label) — label 'current rate' for the latest."""
    segs = freight_segments(rec)
    if not segs:
        return None, "", ""
    day = str(day or dt.date.today().isoformat())[:10]
    pick = None
    for i, (eff, rate) in enumerate(segs):
        if not eff or eff <= day:
            pick = i
    if pick is None:
        pick = 0
    eff, rate = segs[pick]
    last = len(segs) - 1
    label = ("current rate" if pick == last else "previous rate" if pick == last - 1 and len(segs) == 2
             else f"rate from {eff or 'the start'}")
    return rate, eff, label

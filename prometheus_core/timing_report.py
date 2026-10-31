"""Contract-by-contract purchasing-timing analysis for the decision report.

Pure business logic: no Tkinter, files or network. The desktop app hands in
contracts, the stored CBOT history and the figures its own engines already
produce (cost, local price, savings, stock), and this module answers, per
contract, whether the CBOT was fixed at a good time.

What is assessed, and why only that
-----------------------------------
A premium contract has two prices: a premium agreed at signing and a CBOT
fixed later on the pricing date. The stored data records the pricing date
(or pricing lots) but not the signing date, shipment date or lead time, so
the decision whose timing can be judged from the data is *when the CBOT was
fixed*. Moving that date does not move the ship, so it carries no stock risk
of its own; stock coverage is reported beside it from the arrival date.

The CBOT history is one continuous front-month series, while a contract is
priced on a named futures month. The level of the two differ by the spread,
so the contract's own priced CBOT is taken from its own numbers
(CIF ÷ factor − premium, or the CBOT stored on each pricing lot) and only
the *moves* of the history between dates are used:

    alternative CBOT = priced CBOT + (history on alternative day
                                      − history on the actual pricing day)

That assumes the spread between the priced month and the front month held
across the window, which is stated wherever the result is shown.

Hindsight and foresight are kept apart. The best date in the window uses
prices from after the decision and is labelled a hindsight benchmark, never
a claim that it was knowable. The "at the time" figures use only prices on
or before the pricing day.
"""

from __future__ import annotations

import datetime as dt
from bisect import bisect_right

TIMING_REPORT_VERSION = "1.0"

#: CBOT price unit → USD/MT, as the app converts them.
DEFAULT_FACTORS = {"CORN": 0.3937, "SOYBEAN": 0.36745, "WHEAT": 0.36745,
                   "SBM": 1.1023}

DEFAULTS = {
    "window_before_days": 30,    # how far before the pricing day to look
    "window_after_days": 30,     # how far after (hindsight)
    "trailing_obs": 20,          # trading days for the "at the time" view
    "small_opportunity_pct": 1.0,  # below this a timing is Favorable anyway
    "local_band_pct": 1.0,       # ±% of local that counts as Acceptable
    "safety_days": 7,            # stock cover below this was tight
    "ample_days": 30,            # stock cover above this arrived early
    "forward_lookback_obs": 60,  # range used for open, unpriced contracts
    "spike_pct": 2.5,            # one-day jump that reverses = suspect print
}

FAVORABLE, ACCEPTABLE, UNFAVORABLE = "Favorable", "Acceptable", "Unfavorable"
INSUFFICIENT, NOT_APPLICABLE, PENDING = "Insufficient Data", "Not applicable", "Pending"


def _num(value, default=None):
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        return float(str(value).replace(",", ""))
    except Exception:
        return default


def _date(value):
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value or "").strip()[:10])
    except Exception:
        return None


def base_commodity(value):
    return str(value or "").strip().upper().split("-")[0]


# ── market history ────────────────────────────────────────────────────────

class Series:
    """A dated price series that only ever answers on-or-before questions."""

    def __init__(self, pairs):
        clean = {}
        for d, v in pairs:
            d, v = _date(d), _num(v)
            if d is not None and v is not None:
                clean[d] = v
        self.dates = sorted(clean)
        self.values = [clean[d] for d in self.dates]

    def __len__(self):
        return len(self.dates)

    @classmethod
    def from_rows(cls, rows, commodity=None, value_keys=("close", "price"),
                  date_key="date"):
        want = base_commodity(commodity) if commodity else None
        pairs = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            if want and base_commodity(row.get("commodity")) != want:
                continue
            value = next((v for v in (_num(row.get(k)) for k in value_keys)
                          if v is not None), None)
            pairs.append((row.get(date_key), value))
        return cls(pairs)

    def on_or_before(self, day):
        """(value, date) of the last observation on or before ``day``."""
        day = _date(day)
        if day is None or not self.dates:
            return None, None
        i = bisect_right(self.dates, day) - 1
        if i < 0:
            return None, None
        return self.values[i], self.dates[i]

    def between(self, first, last):
        """Observations with first <= date <= last."""
        first, last = _date(first), _date(last)
        return [(d, v) for d, v in zip(self.dates, self.values)
                if (first is None or d >= first) and (last is None or d <= last)]

    def trailing(self, day, count):
        """The last ``count`` observations on or before ``day``."""
        day = _date(day)
        i = bisect_right(self.dates, day)
        lo = max(0, i - int(count))
        return list(zip(self.dates[lo:i], self.values[lo:i]))

    @property
    def last_date(self):
        return self.dates[-1] if self.dates else None

    def spikes(self, pct=DEFAULTS["spike_pct"]):
        """Dates whose price jumps away from both neighbours and comes back.

        A day at least ``pct`` % above (or below) the day before *and* the
        day after, while those two agree with each other, is far more likely
        a stray quote — another futures month stored by mistake — than a
        market move. Such days are kept in the series but never offered as
        a best or worst alternative, and a pricing day that is one is
        flagged.
        """
        out = set()
        v = self.values
        for i in range(1, len(v) - 1):
            a, b, c = v[i - 1], v[i], v[i + 1]
            if not a or not c:
                continue
            up = (b - a) / a * 100.0, (b - c) / c * 100.0
            agree = abs(a - c) / ((a + c) / 2.0) * 100.0 < pct / 2.0
            if agree and ((up[0] >= pct and up[1] >= pct) or (up[0] <= -pct and up[1] <= -pct)):
                out.add(self.dates[i])
        return out


# ── what was priced, and when ────────────────────────────────────────────

def pricing_events(contract, factor):
    """The CBOT fixings of a contract: ``[(date, qty_mt, priced_cbot)]``.

    Pricing lots are used when present (each carries its own CBOT). Else one
    event on the pricing date, with the CBOT implied by the contract's own
    CIF and premium. Returns ``(events, source, reason_if_none)``.
    """
    c = contract or {}
    qty = _num(c.get("qty_mt"))
    premium = _num(c.get("premium_cents"))
    cif = _num(c.get("cif_usd_mt"))
    lots = [x for x in (c.get("pricing_lots") or []) if isinstance(x, dict)]
    events = []
    for lot in lots:
        d, q, cb = _date(lot.get("date")), _num(lot.get("qty_mt")), _num(lot.get("cbot"))
        if d is not None and q and cb is not None:
            events.append((d, q, cb))
    if events:
        return events, "pricing lots", ""
    if premium in (None, 0.0):
        return [], "", "flat price — no CBOT component"
    if not factor:
        return [], "", "no CBOT conversion for this commodity"
    d = _date(c.get("pricing_date"))
    if d is None:
        return [], "", "no pricing date recorded"
    if not cif or not qty:
        return [], "", "no CIF or quantity"
    return [(d, qty, cif / factor - premium)], "pricing date", ""


# ── one fixing against its window ────────────────────────────────────────

def assess_event(event, history, params=None, as_of=None):
    """Hindsight window and at-the-time view for one CBOT fixing."""
    p = dict(DEFAULTS, **(params or {}))
    day, qty, priced = event
    ref, ref_date = history.on_or_before(day)
    if ref is None:
        return {"date": day.isoformat(), "qty_mt": qty, "priced_cbot": priced,
                "status": INSUFFICIENT, "reason": "no CBOT history on or before the pricing day"}
    last = history.last_date
    cap = min(x for x in (_date(as_of), last) if x is not None)
    first = day - dt.timedelta(days=int(p["window_before_days"]))
    end = min(day + dt.timedelta(days=int(p["window_after_days"])), cap)
    window = history.between(first, end)
    if ref_date < first:
        window = [(ref_date, ref)] + window
    suspect = history.spikes(p["spike_pct"])
    # A stray one-day print is never offered as the opportunity; the pricing
    # day itself always stays, since its own contract price confirms it.
    candidates = [(d, v) for d, v in window if d not in suspect or d == ref_date]
    lo_d, lo = min(candidates, key=lambda x: (x[1], x[0]))
    hi_d, hi = max(candidates, key=lambda x: (x[1], -x[0].toordinal()))
    trail = history.trailing(ref_date, p["trailing_obs"])
    trail_vals = [v for _, v in trail]
    avg_then = sum(trail_vals) / len(trail_vals)
    return {
        "date": day.isoformat(), "qty_mt": qty, "priced_cbot": priced,
        "history_on_day": ref, "history_date": ref_date.isoformat(),
        "window_start": window[0][0].isoformat(), "window_end": window[-1][0].isoformat(),
        "window_obs": len(window),
        "window_is_hindsight": end > ref_date,
        "best_date": lo_d.isoformat(), "best_history": lo,
        "best_priced_equivalent": priced + (lo - ref),
        "worst_date": hi_d.isoformat(), "worst_history": hi,
        "opportunity_cbot": ref - lo,                      # ≥ 0 by construction
        "range_position": ((ref - lo) / (hi - lo)) if hi > lo else 0.0,
        "trailing_avg": avg_then, "trailing_low": min(trail_vals),
        "trailing_obs": len(trail_vals),
        "vs_trailing_avg": ref - avg_then,                 # < 0 = below the recent average
        "spikes_excluded": sum(1 for d, _ in window if d in suspect and d != ref_date),
        "pricing_day_is_spike": ref_date in suspect,
        "status": "assessed", "reason": "",
    }


def assess_timing(range_position, opportunity_pct, params=None):
    """Favorable / Acceptable / Unfavorable for an assessed fixing."""
    p = dict(DEFAULTS, **(params or {}))
    if opportunity_pct is not None and opportunity_pct <= p["small_opportunity_pct"]:
        return FAVORABLE
    if range_position <= 1 / 3:
        return FAVORABLE
    if range_position <= 2 / 3:
        return ACCEPTABLE
    return UNFAVORABLE


def contract_timing(contract, history, factor, cost_fx=None, params=None, as_of=None):
    """Timing result for one contract, from its fixings and the history."""
    p = dict(DEFAULTS, **(params or {}))
    c = contract or {}
    qty = _num(c.get("qty_mt"))
    cif = _num(c.get("cif_usd_mt"))
    events, source, why = pricing_events(c, factor)
    out = {"source": source, "events": [], "factor": factor,
           "opportunity_usd_mt": None, "opportunity_usd": None,
           "opportunity_egp": None, "opportunity_pct": None,
           "best_date": "", "best_cbot_equivalent": None, "actual_cbot": None,
           "range_position": None, "vs_trailing_avg": None,
           "window": "", "hindsight": False}
    if not events:
        status = c.get("status") or "Open"
        pricing = str(c.get("pricing_status") or "").upper()
        if why == "no pricing date recorded" and status == "Open" and pricing in ("", "UNPRICED"):
            out.update(status=PENDING, assessment=PENDING,
                       reason="open and unpriced — the CBOT is still to be fixed",
                       forward=forward_view(history, p, as_of))
            return out
        label = NOT_APPLICABLE if why.startswith("flat price") or why.startswith("no CBOT conv") else INSUFFICIENT
        out.update(status=label, assessment=label, reason=why)
        return out
    if len(history) == 0:
        out.update(status=INSUFFICIENT, assessment=INSUFFICIENT,
                   reason="no CBOT history stored for this commodity")
        return out

    assessed = [assess_event(e, history, p, as_of) for e in events]
    good = [a for a in assessed if a["status"] == "assessed"]
    out["events"] = assessed
    if not good:
        out.update(status=INSUFFICIENT, assessment=INSUFFICIENT, reason=assessed[0]["reason"])
        return out
    q = sum(a["qty_mt"] for a in good)
    wavg = lambda key: sum(a[key] * a["qty_mt"] for a in good) / q
    opp_cbot = wavg("opportunity_cbot")
    opp_usd_mt = opp_cbot * factor
    biggest = max(good, key=lambda a: a["opportunity_cbot"] * a["qty_mt"])
    opp_usd = opp_usd_mt * q       # only the tonnes actually priced
    out.update(
        status="assessed", reason="",
        qty_priced=q, actual_cbot=wavg("priced_cbot"),
        best_cbot_equivalent=wavg("best_priced_equivalent"),
        best_date=biggest["best_date"],
        opportunity_usd_mt=opp_usd_mt, opportunity_usd=opp_usd,
        opportunity_egp=(opp_usd * cost_fx) if cost_fx else None,
        opportunity_pct=(opp_usd_mt / cif * 100.0) if cif else None,
        range_position=wavg("range_position"),
        vs_trailing_avg=wavg("vs_trailing_avg"),
        window=f"{min(a['window_start'] for a in good)} → {max(a['window_end'] for a in good)}",
        hindsight=any(a["window_is_hindsight"] for a in good),
        priced_share=min(1.0, q / qty) if qty else None,
        spikes_excluded=sum(a["spikes_excluded"] for a in good),
        confidence=("Low — the stored CBOT on the pricing day is a one-day outlier"
                    if any(a["pricing_day_is_spike"] for a in good) else "Normal"),
    )
    out["assessment"] = assess_timing(out["range_position"], out["opportunity_pct"], p)
    return out


def forward_view(history, params=None, as_of=None):
    """For a CBOT not yet fixed: where today's price sits in its recent range.

    Forward-looking context only — it says nothing about where the price
    goes next, and is labelled that way.
    """
    p = dict(DEFAULTS, **(params or {}))
    if len(history) == 0:
        return None
    day = _date(as_of) or history.last_date
    recent = history.trailing(day, p["forward_lookback_obs"])
    if not recent:
        return None
    vals = [v for _, v in recent]
    now, now_d = history.on_or_before(day)
    lo, hi = min(vals), max(vals)
    return {"current": now, "current_date": now_d.isoformat() if now_d else "",
            "low": lo, "high": hi, "obs": len(vals),
            "range_position": ((now - lo) / (hi - lo)) if hi > lo else 0.0}


# ── savings against local and stock at arrival ───────────────────────────

def assess_local(saving_mt, local_price, params=None):
    p = dict(DEFAULTS, **(params or {}))
    saving_mt, local_price = _num(saving_mt), _num(local_price)
    if saving_mt is None or not local_price:
        return INSUFFICIENT
    pct = saving_mt / local_price * 100.0
    if pct >= p["local_band_pct"]:
        return FAVORABLE
    if pct <= -p["local_band_pct"]:
        return UNFAVORABLE
    return ACCEPTABLE


SCORE = {FAVORABLE: 1, ACCEPTABLE: 0, UNFAVORABLE: -1}


def final_assessment(local, timing):
    """One verdict per contract from its local result and its timing.

    Local missing → Insufficient Data. Timing not assessable (insufficient,
    not applicable, pending) → the local result stands alone. Both present →
    score them Favorable +1, Acceptable 0, Unfavorable −1 and add: +1 or more
    is Favorable, 0 Acceptable, −1 or less Unfavorable. A good buy with bad
    timing (or the reverse) therefore lands on Acceptable.
    """
    if local not in SCORE:
        return INSUFFICIENT
    if timing not in SCORE:
        return local
    total = SCORE[local] + SCORE[timing]
    return FAVORABLE if total >= 1 else (UNFAVORABLE if total <= -1 else ACCEPTABLE)


def stock_before(lots, draws, day):
    """Tonnes in the yard at the start of ``day``: landed before − used before."""
    day = _date(day)
    if day is None:
        return None
    landed = sum(_num(l.get("original_mt") or l.get("qty_mt"), 0.0) or 0.0
                 for l in lots or [] if (_date(l.get("delivery_date")) or dt.date.max) < day)
    used = sum(_num(d.get("mt"), 0.0) or 0.0 for d in draws or []
               if (_date(d.get("date")) or dt.date.max) < day
               and (d.get("contract_ref") or "") != "(unsourced)")
    return max(landed - used, 0.0)


def arrival_coverage(stock_mt, daily_rate, qty_mt, params=None):
    """What the stock said when the cargo arrived, in days and in words."""
    p = dict(DEFAULTS, **(params or {}))
    rate = _num(daily_rate)
    if stock_mt is None or not rate:
        return {"cover_days": None, "cargo_days": None, "verdict": INSUFFICIENT,
                "explain": "no daily consumption rate or stock record"}
    cover = stock_mt / rate
    cargo = (_num(qty_mt, 0.0) or 0.0) / rate
    if cover <= 0.5:
        verdict, explain = ("Needed — yard empty",
                            "stock had run out before it arrived; any later arrival meant a longer stoppage")
    elif cover < p["safety_days"]:
        verdict, explain = ("Needed — prevented shortage",
                            f"only {cover:,.1f} days of stock left; arriving later would have caused a shortage")
    elif cover <= p["ample_days"]:
        verdict, explain = ("Timely", f"{cover:,.1f} days of stock on hand; it could have arrived "
                            f"up to {max(cover - p['safety_days'], 0):,.0f} days later without a shortage")
    else:
        verdict, explain = ("Early — stock was ample",
                            f"{cover:,.1f} days of stock on hand; it arrived well before it was needed")
    return {"cover_days": cover, "cargo_days": cargo, "verdict": verdict, "explain": explain,
            "max_safe_delay_days": max(cover - p["safety_days"], 0.0)}


# ── the dashboard ────────────────────────────────────────────────────────

def executive_summary(rows):
    """Totals that never add one kind of saving to another.

    Savings against local (realized and estimated kept apart) and the
    hindsight timing opportunity answer different questions; they are
    reported side by side and never summed.
    """
    def total(key, pred=lambda r: True):
        return sum(r[key] for r in rows if pred(r) and isinstance(r.get(key), (int, float)))
    realized = lambda r: r.get("saving_kind") == "Realized"
    estimated = lambda r: r.get("saving_kind") == "Estimated"
    t = lambda r: r.get("timing") or {}
    counts = {}
    for r in rows:
        counts[r.get("final_assessment")] = counts.get(r.get("final_assessment"), 0) + 1
    timing_counts = {}
    for r in rows:
        a = t(r).get("assessment")
        timing_counts[a] = timing_counts.get(a, 0) + 1
    ranked = sorted((r for r in rows if isinstance(t(r).get("opportunity_usd"), (int, float))),
                    key=lambda r: -t(r)["opportunity_usd"])
    return {
        "contracts": len(rows),
        "contract_value_usd": total("contract_value_usd"),
        "contract_value_egp": total("contract_value_egp"),
        "quantity_mt": total("qty_mt"),
        "saving_local_realized_egp": total("saving_local_egp", realized),
        "saving_local_estimated_egp": total("saving_local_egp", estimated),
        "timing_opportunity_usd": sum(t(r)["opportunity_usd"] for r in ranked),
        "timing_opportunity_egp": sum(t(r).get("opportunity_egp") or 0.0 for r in ranked),
        "timing_assessed": len(ranked),
        "timing_favorable": timing_counts.get(FAVORABLE, 0),
        "timing_acceptable": timing_counts.get(ACCEPTABLE, 0),
        "timing_unfavorable": timing_counts.get(UNFAVORABLE, 0),
        "timing_insufficient": timing_counts.get(INSUFFICIENT, 0),
        "timing_not_applicable": timing_counts.get(NOT_APPLICABLE, 0),
        "timing_pending": timing_counts.get(PENDING, 0),
        "missed_savings": sum(1 for r in ranked if t(r).get("assessment") == UNFAVORABLE),
        "needs_review": sum(1 for r in rows if r.get("final_assessment") in (UNFAVORABLE, INSUFFICIENT)
                            or t(r).get("assessment") == INSUFFICIENT),
        "final_counts": counts,
        "ranking": [r.get("id") for r in ranked],
    }

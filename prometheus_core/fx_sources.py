"""Bank FX rates, parsed out of a published rate page.

Why this exists
---------------
The app's default rate comes from Frankfurter, which publishes an official
*mid* rate and updates once a working day. An importer never trades at the
mid: buying USD means paying the bank's **sell** side, and in Egypt the gap
between a reference mid and a commercial bank's sell rate is large enough to
move a landed cost by hundreds of EGP per tonne. A bank page is both fresher
and the rate actually paid.

What this module does *not* do
------------------------------
It does not hard-code one bank's page structure. Bank sites change markup
without notice, and a scraper pinned to today's HTML is a bug waiting for a
redesign. Instead the parser looks for the shape every rate table shares — a
row that names the currency, followed by two plausible numbers — and the URL
is configurable so a move or a different bank needs no code change.

Everything here is pure: text in, numbers out. The network call lives in the
app, so this stays unit-testable without one.
"""

from __future__ import annotations

import json
import re

__all__ = ["CIB_DEFAULT_URL", "FX_SOURCE_FRANKFURTER", "FX_SOURCE_CIB",
           "FX_SOURCE_MANUAL", "FX_SOURCES", "parse_bank_rates",
           "pick_costing_rate"]

#: Commercial International Bank's published rate page.  Editable in the app:
#: if CIB moves it, point the setting at the new address rather than waiting
#: for a new build.
CIB_DEFAULT_URL = "https://www.cibeg.com/en/personal/rates-and-fees/exchange-rates"

FX_SOURCE_FRANKFURTER = "Frankfurter (official mid)"
FX_SOURCE_CIB = "CIB bank rate"
FX_SOURCE_MANUAL = "Manual entry"

FX_SOURCES = [FX_SOURCE_FRANKFURTER, FX_SOURCE_CIB, FX_SOURCE_MANUAL]

#: A USD/EGP rate outside this band is a page-furniture number — a phone
#: number, a year, a percentage — not a quote.  Wide enough to survive years
#: of devaluation, tight enough to reject noise.
_PLAUSIBLE = (5.0, 500.0)

#: How the currency is named across English and Arabic rate tables.
_USD_WORDS = ("USD", "US DOLLAR", "U.S. DOLLAR", "US$", "AMERICAN DOLLAR",
              "دولار")

_TAG = re.compile(r"<[^>]+>")
# Matched as whole tokens: an unanchored alternation chopped "19666" into
# "196" and "66", and 66 looks like a plausible rate.  The boundaries make
# a long digit run stay one number, so it fails the plausibility band.
_NUMBER = re.compile(r"(?<![0-9.,])[0-9][0-9,]*(?:\.[0-9]+)?(?![0-9,])")


def _clean(text):
    """HTML to plain text, one line per row, entities folded."""
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", text or "")
    text = re.sub(r"(?i)</(tr|div|p|li|table)>", "\n", text)
    text = re.sub(r"(?i)</t[dh]>", " | ", text)
    text = _TAG.sub(" ", text)
    for entity, char in (("&nbsp;", " "), ("&amp;", "&"), ("&#160;", " ")):
        text = text.replace(entity, char)
    return text


def _numbers(line):
    out = []
    for match in _NUMBER.findall(line):
        try:
            value = float(match.replace(",", ""))
        except ValueError:
            continue
        if _PLAUSIBLE[0] <= value <= _PLAUSIBLE[1]:
            out.append(value)
    return out


def _from_json(payload, currency):
    """Pull buy/sell out of a JSON rate feed, whatever it calls the fields."""
    found = {}

    def walk(node):
        if isinstance(node, dict):
            label = " ".join(
                str(node.get(key, "")) for key in
                ("currency", "code", "currencyCode", "symbol", "name")).upper()
            if any(word in label for word in _USD_WORDS):
                for key, value in node.items():
                    low = key.lower()
                    try:
                        number = float(str(value).replace(",", ""))
                    except (TypeError, ValueError):
                        continue
                    if not _PLAUSIBLE[0] <= number <= _PLAUSIBLE[1]:
                        continue
                    if "buy" in low or "bid" in low:
                        found.setdefault("buy", number)
                    elif "sell" in low or "ask" in low or "offer" in low:
                        found.setdefault("sell", number)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    if found.get("buy") is not None or found.get("sell") is not None:
        return found
    return None


def parse_bank_rates(text, currency="USD"):
    """Find the buy and sell rate for ``currency`` in a rate page.

    Accepts HTML or JSON. Returns ``{"buy": float|None, "sell": float|None,
    "line": str}``; every field may be ``None`` when the page does not hold a
    usable quote, which the caller is expected to report rather than paper
    over with a stale number.

    Rate tables order the pair buy-then-sell, and a bank always sells a
    currency for more than it buys it. When the two are the wrong way round
    they are swapped, so a page that lists sell first still reads correctly.
    """
    raw = text or ""
    stripped = raw.strip()
    if stripped[:1] in "{[":
        try:
            found = _from_json(json.loads(stripped), currency)
        except (ValueError, TypeError):
            found = None
        if found:
            buy, sell = found.get("buy"), found.get("sell")
            if buy is not None and sell is not None and buy > sell:
                buy, sell = sell, buy
            return {"buy": buy, "sell": sell, "line": "json feed"}

    words = _USD_WORDS if currency.upper() == "USD" else (currency.upper(),)
    best = None
    for line in _clean(raw).splitlines():
        flat = " ".join(line.split())
        if not flat:
            continue
        upper = flat.upper()
        if not any(word in upper for word in words):
            continue
        numbers = _numbers(flat)
        if not numbers:
            continue
        # Prefer the tightest row that names the currency: a navigation blurb
        # mentioning "US Dollar" carries one stray number, a rate row two.
        rank = (len(numbers) >= 2, -len(flat))
        if best is None or rank > best[0]:
            best = (rank, numbers, flat)

    if best is None:
        return {"buy": None, "sell": None, "line": ""}

    _rank, numbers, line = best
    if len(numbers) == 1:
        return {"buy": None, "sell": numbers[0], "line": line}
    buy, sell = numbers[0], numbers[1]
    if buy > sell:
        buy, sell = sell, buy
    return {"buy": buy, "sell": sell, "line": line}


def pick_costing_rate(buy, sell):
    """The rate an importer actually pays, with why it was chosen.

    Buying goods abroad means buying USD, so the bank's **sell** side is the
    cost. Falling back to the buy side understates every landed cost by the
    spread, so when only the buy side is published the caller is told.
    """
    if sell is not None:
        return sell, "bank sell rate — what you pay to buy USD"
    if buy is not None:
        return buy, "bank buy rate — sell side not published, understates cost"
    return None, "no rate found"

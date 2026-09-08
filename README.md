# Prometheus Procurement V10.9.2

Daily FIFO Inventory + Inventory vs Market + Scenario Lab release, built on the latest V10.8.15 source and preserving the existing `app_state.json`.

## Run

Double-click:

```text
run_prometheus.bat
```

or run:

```text
python Prometheus_V10_9_2.py
```

The app continues to read/write the normal state file under:

```text
Documents\ImportDecisionApp\app_state.json
```

## The interface

Prometheus runs the **Aurora** interface: a left navigation rail grouped by
the daily loop (Market / Transact / Decide / Operate), a top bar with the
page title, live FX and CBOT chips and a jump box, and a `Ctrl+K` command
palette for going straight to any screen.

- **Day and Night themes.** Toggle from the top bar, or from
  **Setup & Data → Appearance**. Applied immediately — no restart.
- **Classic chrome is still there.** The same Appearance panel switches
  back to the original tab bar. Every screen, calculation and export is
  identical either way.
- Keyboard: `Ctrl+K` jump · `Ctrl+R` refresh · `Ctrl+S` snapshot ·
  `Ctrl+E` export PDF.

## CBOT Command Center

The first destination on the rail — everything the CBOT decision needs, on
one screen, before you price anything:

- Live board price for **CORN / SBM / SOYBEAN / WHEAT**, its 30-day move
  and how old the stored quote is.
- Indicative **replacement cost EGP/MT** from today's board, the
  quantity-weighted premium of the open book and today's FX. If there is no
  defensible premium, the figure is labelled *flat (zero basis)* rather
  than presented as an estimate.
- **Board history** over 30D / 90D / 6M / 1Y / All, with a hover readout.
- **Price cover**: how much of the open book is priced, how much is still
  exposed to CBOT, and how much value has no Form 4 FX yet.
- **Where today sits** inside the stored 12-month band, and the goods-only
  gap between CBOT-implied and the latest local all-in. Freight, clearing,
  VAT and finance are *not* in that gap — Analysis → Inventory vs Market is
  the landed comparison.
- **Open price risk**: unpriced tons first, nearest delivery first, click
  through to the contract.
- **Signals**: stale quotes, tons unpriced inside the alert window, FX not
  secured, and large 30-day board moves.

All of it is read from the data the app already stores (`market_data`,
`cbot_history`, `fx_history`, `local_prices`, `contracts`). Nothing on this
screen invents a number: a missing input is shown as missing.

## Daily FIFO inventory

Home now includes **Current FIFO Inventory**. Inventory membership is based on physical delivery and FIFO consumption, not the contract Open/Closed label:

- Delivered Closed contracts stay in current inventory until their tons are consumed.
- Delivered Open contracts may be current inventory.
- Future Open contracts remain **Inbound / Pipeline** and are not mixed into current stock.
- Oldest delivered inventory is consumed first.
- A physical stock-count adjustment becomes the new confirmed stock baseline.

For each commodity the app shows:

- Current remaining FIFO MT
- ACTUAL / ESTIMATED status
- Quantity-weighted average inventory cost EGP/MT
- Latest comparable local all-in price
- Current Inventory Edge EGP/MT and total EGP
- Oldest remaining contract/date
- Newest remaining contract/date
- Open inbound MT and unpriced inbound MT
- Coverage days
- Last physical-stock baseline

Double-click a commodity row to open the FIFO lot reconciliation.

## Automatic daily estimate

When there is no actual consumption entry after the latest physical baseline, Prometheus can roll inventory forward analytically using the configured MT/day consumption rate. This is labelled **ESTIMATED** and never creates fake consumption-log rows.

The estimate recalculates on startup/Home refresh and when the date, consumption, receipts, contracts, local price, CBOT or FX context changes. If estimated consumption exceeds identifiable stock/receipts, the app displays a FIFO shortage/data warning rather than creating negative inventory.

Enter a new physical stock count at any time to re-anchor the model to reality.

## Inventory vs Market

Analysis now includes **Inventory vs Market**, a compact remaining-stock table modeled on the Open Contracts MTM view. It uses FIFO **Remaining MT**, not original contract quantity.

Default filters are `CORN` + `Open`, with `All / Open / Closed` contract-status options. Delivered Open and Closed contracts can both remain physical inventory; future contracts stay inbound and fully consumed lots disappear.

For every remaining contract layer the table shows:

- Contract, supplier, commodity/origin and status
- Pricing status and FIFO Remaining MT
- Historical FIFO cost EGP/MT
- Live CBOT and the explicit `(CBOT + premium) × factor` formula
- Current USD/EGP
- Current route/commodity freight including 14% VAT
- Current CBOT replacement cost EGP/MT
- Latest comparable local all-in EGP/MT
- Edge vs Local EGP/MT
- Edge vs CBOT Replacement EGP/MT
- A plain-language decision

Positive edge means the already-owned stock is cheaper than today's alternative. Historical FIFO cost is never revalued with today's FX. Replacement pricing uses today's FX. If a positive/defensible premium is missing, the CBOT replacement comparison remains blank rather than assuming zero.

The table is quantity-weighted at commodity subtotal level and can be exported to Excel. Home has an **Inventory vs Market →** shortcut, and the FIFO lot-detail window links to it as well.

## Market comparison

**Current Inventory Edge** is separate from historical Realised Saving:

```text
Inventory Edge / MT = Latest Local All-In EGP/MT - Weighted FIFO Inventory Cost EGP/MT
Total Inventory Edge = Inventory Edge / MT × Current FIFO MT
```

For CBOT commodities the app also calculates an indicative replacement cost from current CBOT, a defensible remaining-inventory premium, current FX and current replacement fees. If no defensible premium exists, the replacement comparison is explicitly incomplete rather than assuming zero.

## Freight VAT

Contract freight supports:

- `DETAILED`: base freight + VAT % (default 14%).
- `ALL_IN`: entered freight is already final; VAT is not added again.
- `LEGACY`: historical stored freight is preserved unchanged until explicitly edited.

This prevents silent historical repricing and VAT double counting.

## Scenario Lab

Open **Analysis → Scenario Lab** to change CBOT, FX, premium, local price, local transport, freight/VAT, purchase quantity, consumption and horizon without overwriting source market, contract or consumption data.

Available actions:

- Reset to Current Market
- Save Scenario
- Compare Scenarios
- Export Scenario Excel
- Open FIFO Lot Detail

## Contracts workspace retained

V10.8.15 features remain available, including Delivery-Date sorting, filtered/all-contract Excel exports, Pricing Lots export and two-contract comparison.

## Tests

From this folder:

```text
run_tests.bat
```

or:

```text
python -m unittest discover -s tests -v
```

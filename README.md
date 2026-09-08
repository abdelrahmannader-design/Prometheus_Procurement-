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

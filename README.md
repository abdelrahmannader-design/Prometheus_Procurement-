# Prometheus Procurement V10.9.10 — Aurora Stress Reconciliation

> How every analysis tab calculates its results: see [ANALYSIS_GUIDE.md](ANALYSIS_GUIDE.md).

## V10.9.10 focus — Deal Calculator / Stress Test reconciliation

- Fixed a material inconsistency where the Single Deal Calculator included finance carry but the Stress Test base case did not.
- Stress Base now uses the same direct landed-cost economics as Calculate: `(CIF USD/MT + finance carry USD/MT) × FX + direct intake`.
- Finance days and annual interest rate are now passed into the Stress/Recommendation engine.
- Break-even FX and Break-even CBOT now include finance carry.
- Formula-based Stress Excel now exposes Finance Days and Annual Interest Rate as editable assumptions and includes carry in every live formula.
- The Stress panel now states whether finance carry is included.
- Example regression from the reported screen: CBOT 530.75, premium 180, FX 51.184, local 14,600, direct intake 235, 30 finance days @ 22% now reconciles to `-220 EGP/MT` in both Calculate and Stress Base, instead of `-220` vs `+43`.

## V10.9.9 focus — auditable FX exposure

- CEO Brief now separates **FX Secured MT** from **FX Still Floating MT** instead of showing only a percentage.
- Portfolio FX coverage is traceable to the exact uncovered contract references and quantities.
- Every commodity CEO page shows Open MT, CBOT-unpriced MT, FX-secured MT, FX-floating MT, coverage %, and uncovered FX contract references.
- Home Executive Summary now reads **FX Secured** and displays both secured and floating MT.
- FX exposure remains separate from CBOT pricing exposure and from FIFO physical inventory.
- FX coverage is quantity-based across OPEN contracts; a valid Form 4 FX rate marks that contract quantity as secured. Delivery date does not remove open FX exposure.

## V10.9.8 focus — explicit Open / Unpriced exposure

- Contracts now have an explicit **Pricing status**: Unpriced, Partially Priced, or Priced.
- **Open + Unpriced** is counted as CBOT price exposure regardless of whether the planned delivery date is past, today, or future.
- Contracts has a **Pricing** filter and an **Open Unpriced** KPI.
- Multi-select contracts and use **Mark Unpriced** / **Mark Priced** for fast cleanup of the current open book.
- CEO commodity briefs now separate **Open contracted quantity**, **Open unpriced exposure**, and **Future-dated inbound**.
- Existing FIFO inventory remains a physical/inventory concept; pricing exposure is not mixed with FIFO or future-inbound logic.
- Legacy contract records remain compatible: status is inferred from pricing lots / CIF / legacy `priced` when no explicit pricing status exists.


This release is built on the user's attached **V10.9.2 Aurora Interface 996** package. It preserves the Aurora visual design and existing `app_state.json` compatibility while upgrading FIFO/Scenario Excel exports, Local Purchase integration, wide-screen usability, and CEO reporting.

## Run

Double-click:

```text
run_prometheus.bat
```

or run:

```text
python Prometheus_V10_9_10.py
```

Prometheus continues to read/write its normal state file under:

```text
Documents\ImportDecisionApp\app_state.json
```


## V10.9.7 focus

This point release fixes the Inventory vs Market table mapping and adds persistent date-order controls without changing FIFO or market economics.

- **Inventory vs Market:** Source / Ref / Supplier / Commodity / Origin / Status / Pricing are aligned with the correct values in both Executive and Full Audit views.
- **Local Prices:** choose `Newest → Oldest` or `Oldest → Newest`.
- **FX Daily History:** same date-order choice.
- **CBOT Daily Close History:** same date-order choice.
- `Newest → Oldest` is the default when no preference has been saved. The chosen display order is remembered in `ui` settings.
- Sorting is display-only and does not rewrite historical data or calculations.

## V10.9.6 highlights

### Formula-based FIFO Excel

The FIFO export is now a management workbook rather than a flat dump. It contains:

- **FIFO Summary** — quantity-weighted stock/cost/market KPIs and a management chart.
- **FIFO Layers** — source, supplier/contract, FIFO quantities, cost, local comparison, CBOT replacement and edge calculations.
- **Assumptions** — market and cost assumptions used by the formulas.

Key result cells are Excel formulas, so editable assumptions recalculate the workbook in Excel. Formatting includes filters, frozen panes, number formats, conditional formatting, visual section headers and charts.

### Formula-based Scenario Lab Excel

Scenario Lab export now contains editable assumptions and formula-driven outputs for:

- CBOT, premium/basis and FX
- local base price and transport
- freight mode, VAT and other costs
- purchase quantity and purchase source
- consumption quantity/horizon
- post-purchase weighted inventory cost
- local edge, import benchmark and projected coverage

A **Current FIFO Sources** sheet provides an auditable breakdown of the inventory position feeding the scenario.

### Local Purchases are part of FIFO and Scenario Lab

Actual Local Purchases are now normalized into the same FIFO lot stream as imports. A Local Purchase enters inventory on its purchase date at:

```text
Local Purchase FIFO Cost = Local Price EGP/MT + Local Transport EGP/MT
```

FIFO depletion remains oldest-first across both import and local lots. Scenario Lab shows the current Import FIFO / Local FIFO mix and can model the proposed purchase as either **IMPORT / CBOT** or **LOCAL PURCHASE**.

### Calculate and FIFO wide-content fixes

The Calculate page no longer nests a second scrolling canvas inside the Aurora page canvas. This removes the large blank/clipped viewport seen in the supplied screenshot and leaves Aurora as the single scroll owner.

FIFO and Inventory vs Market wide tables now expose proper horizontal/vertical scrolling. Inventory vs Market includes **Executive** and **Full Audit** column views so management can use a compact view without losing the detailed audit columns.

### Commodity-by-commodity CEO Brief

The CEO Brief PDF now starts with a portfolio summary and then creates a decision page for each available commodity. Commodity pages emphasize the information management actually needs:

- current FIFO stock and weighted cost
- remaining inventory value
- Import FIFO vs Local FIFO mix
- latest local market and inventory edge
- CBOT, premium, FX and replacement economics when applicable
- edge vs CBOT replacement
- coverage days
- oldest/newest remaining FIFO lot
- open inbound and unpriced exposure
- realised performance context
- material FIFO/data-quality warnings

### CEO Email Digest export center

Analysis now contains a **CEO Email Digest** tab. It lets the user choose the app outputs to include, use **Select All / Clear / Executive Pack**, and choose:

- **Grouped email** — selected outputs bundled into one digest workflow.
- **Separate emails** — selected outputs handled individually.

The export catalog includes the CEO Brief, FIFO, Scenario Lab, Inventory vs Market, Local Purchases, Contracts, Finance, Basis and state/audit outputs where available.

## Existing Aurora interface

The left navigation rail, top market chips, command palette, Day/Night themes and classic-interface fallback remain intact. The release intentionally avoids changing the Aurora design system.

## Build Windows EXE

Use:

```text
build_exe_onedir.bat
```

The generated `onedir` build must be distributed as the entire output folder, including PyInstaller's support files.

## Validation

Run:

```text
run_tests.bat
```

or:

```text
python -m unittest discover -s tests -v
```

See `VALIDATION.txt` for the release validation summary.

### V10.9.7 usability fixes
- Inventory vs Market table column mapping corrected (Source / Ref / Supplier / Commodity / Origin / Status / Pricing).
- Local Prices, USD/EGP Daily History and CBOT Daily Close History each have a persistent order selector: Newest → Oldest or Oldest → Newest.

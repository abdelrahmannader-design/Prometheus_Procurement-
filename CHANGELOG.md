# Changelog

## Unreleased — Formula-based Contract Comparison + Basis Tracker charts

- Rewrote the two-contract comparison Excel export
  (`_build_contract_comparison_workbook`) to be formula-based: CIF, FX,
  fees, CBOT-at-date and local price are written as input cells, and every
  derived figure (Contract Goods, Own-After, Market Price, Saving, Total
  Saving) is a live Excel formula referencing those inputs in the same
  column — edit an input and the rest of that contract's column
  recalculates.
- Added "Market Price at Pricing Date" and "Market Price at Delivery
  (receiving) Date" to the comparison, each showing CBOT, FX, and the
  resulting market price in USD/MT and EGP/MT — resolved via the same
  `_basis_contract_cbot`/`_basis_contract_fx` engine Basis Tracker uses,
  so the figures always agree with Basis Tracker for the same contract and
  date. New `_contract_market_at_date()` helper.
- Added a clustered bar chart to the comparison export (Contract Goods,
  Own-After, Local, Market @ Pricing, Market @ Delivery, Saving — A vs B),
  fed by cells that mirror the live formulas so the chart stays in sync
  with edits.
- Added a line chart with marker points to the Basis Tracker Excel export
  (`_build_basis_excel_workbook`): Contract Basis and Implied Basis (or,
  for SBM, Contract/Local Equivalent Price) plotted over time, one point
  per date. Rows are now sorted by date before writing so the chart reads
  chronologically.

Verified headlessly: built two contracts with CBOT/FX/local history
spanning both pricing and delivery dates, exported the comparison and
confirmed every formula cell references the correct row and evaluates to
the same number the app's own economics engine produces; exported Basis
Tracker with 76 rows and confirmed the chart renders. No exceptions in
either path.

## Unreleased — Bug fixes (Contract Performance Excel export)

`export_performance_excel` was completely broken and would crash on every
single use — found while reviewing the app's historical error_log.txt.
Fixed several accumulated issues:
- `FormulaRule(..., dxf=...)` isn't valid in the installed openpyxl —
  `FormulaRule` builds its own differential style from `font`/`fill`
  kwargs and doesn't accept a pre-built one. Switched both conditional
  formatting blocks to pass `fill=`/`font=` directly.
- `cell.font.color.rgb` crashed with `AttributeError` on default cells
  (no color set → `font.color` is `None`). Added a `None` guard.
- The second ("printable summary") sheet the export builds referenced
  `row["vessel"]`, `row["d_from"/"d_to"/"n_points"]`, `row["avg_local"]`
  and `row["cum_sav_egp"]` — none of which `run_performance()` actually
  stores — and iterated `row["rows"]` (a list of plain tuples) with
  dict-style access (`row_d["date"]`, `row_d.get("is_pre")`, etc.). None
  of this matched the real data shape `run_performance()` produces.
  Rewrote both the formula-based sheet and the printable-summary sheet to
  consume the real `(label, local, own_after, sav_mt, cum_avg, signal)`
  tuples, dropped the now-nonexistent "pre-delivery" row concept, and
  derived the analysis-period label from the row dates instead of a
  missing field.

Verified end-to-end headlessly: built a closed contract with logged local
prices, ran the Contract Performance analysis, and exported to Excel —
completes with the chart and conditional formatting intact and no
exceptions, where it previously crashed immediately.

## Unreleased — CEO Dashboard Enhancements

- Added an Executive Summary panel to Home: YTD realised-savings vs an
  editable annual target (with a run-rate projection to year end), a daily
  Open Exposure Trend chart driven by the existing open-MTM snapshot log,
  portfolio-wide FX hedge coverage (share of open MT with Form 4 FX
  secured), and a cash-due calendar (overdue / ≤30 / 31-60 / 61-90 days)
  estimated from own-after cost x quantity.
  - Refactored the commodity portfolio cards into a Category Performance
  table: closed/open MT, realised and indicative EGP, YTD realised, and a
  year-over-year comparison against the same period last year, per
  commodity.
- Added a one-click "CEO Brief (PDF)" export on Home: headline KPIs, YTD
  target pace, FX cover, cash calendar, category performance and the top
  open alerts on a single exportable page.
- Added an "Annual savings target (EGP)" setting under Setup & Data →
  Decision Settings, driving the new YTD progress bar.
- Added a "Value created since go-live" headline on the Home hero banner —
  all-time closed-contract realised savings, distinct from the YTD figure.
- Added a Forward Landed-Cost Trend line to the Executive Summary: a
  transparent 90-day linear extrapolation of logged CBOT + FX history into
  a projected landed cost, clearly labelled as a trend line, not a forecast
  guarantee.
- Added a CEO Email Digest under Setup & Data → Data Management: SMTP
  settings, a "Send Test Brief Now" button, and an optional auto-send
  (every N days while the app is open) that emails the CEO Brief PDF.
- Added a High-priority Action Center alert when the YTD savings run-rate
  projects materially (>=15%) short of the annual target.
- Category Performance rows on Home are now clickable — jumps to the
  Contracts tab pre-filtered to that commodity, replacing the old
  commodity-card click behaviour.

## V10.8.15 — Modern Contracts Workspace

- Added Delivery Date as a primary Contracts-table column.
- Defaulted the Contracts table to Delivery Date newest-first, with explicit alternate sort options.
- Added Export All Contracts and Export Visible/Filtered Contracts Excel actions.
- Added Summary, Contracts and Pricing Lots sheets to the new export.
- Added a two-contract side-by-side comparison window and comparison Excel export.
- Preserved V10.8.14 as `legacy/V10_8_14_Frozen.py`.
- Kept all contract formulas and saved-state fields unchanged.

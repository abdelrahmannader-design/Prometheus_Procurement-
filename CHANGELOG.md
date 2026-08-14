# Changelog

## Unreleased — Fix: unrealistic Local Purchases CBOT Equivalent

User-flagged: the Local Purchases CBOT Equivalent added last round was
still unrealistic — e.g. a real CORN local buy implied CBOT ≈ 665 while
the period's actual Avr CBOT was ≈ 450, a ~215-point gap. Root cause: the
formula assumed a zero-basis (flat) local price, but a local buy's price
always carries a real basis/premium over CBOT — with nothing to net that
back out, the entire basis got misread as CBOT, every time, for every
local row.

Fixed by netting out this period's average import premium per commodity
(computed from the brief's own Import contract rows) instead of assuming
zero:

`CBOT Equivalent = ((price+transport−expenses)÷FX)÷factor − avg import premium`

- New editable "Avg import premium this period" cell in Assumptions (B4 in
  Finance Brief, B5 in Period Brief) when the brief is filtered to one
  commodity — auto-computed but editable to test a different assumption.
- New "Premium used (¢/bu)" column in both briefs' Local Purchases tables,
  so which premium was netted out is visible per row, not hidden inside
  the formula. Mixed "ALL" briefs use each row's own commodity's average,
  embedded as a literal.
- Rows for a commodity with no import contracts in the brief (nothing to
  average) fall back to 0 and are flagged red with a legend note — the
  figure is then a zero-basis upper bound, not a real estimate.

Verified against the real numbers from the user's uploaded brief: the
215-point gap closes to ~16 points (664.5 → 465.8 vs Avr CBOT 449.6).
Re-ran the full regression suite — no exceptions, no regressions in any
of the six earlier fix areas.

## Unreleased — CBOT Equivalent (Implied) for Local Purchases

Period Brief and Finance Brief only ever computed "CBOT Equivalent
(Implied)" for import-contract rows. Local purchases have no CIF/premium
to work from, so they got nothing. Added a Local Purchases section to
Finance Brief (which previously omitted local purchases entirely) and a
new "CBOT Equivalent (Implied)" column to both briefs' Local Purchases
tables, for every commodity:

`CBOT Equivalent = ((price + transport − local expenses) ÷ FX) ÷ factor`

— i.e. the flat CBOT print a zero-basis deal would need to justify that
local price, directly comparable to the Avr CBOT column. CBOT Ref/FX for
each row come from the purchase's own recorded `cbot_ref`/`fx_ref` when
present, otherwise the nearest logged CBOT/FX history on or before the
purchase date (same lookup the Local Purchases tab's auto-fill button
uses) — cells that fall back to history are marked gray/italic with a
legend note, so a looked-up estimate is never mistaken for a recorded
figure. Uses the same single-commodity-aware Assumptions factor as the
CBOT Equivalent fix above (own factor when filtered to one commodity,
literal per-row factor in mixed "ALL" briefs).

Verified headlessly: a CORN local buy with recorded CBOT/FX renders
un-marked and uses Assumptions!$B$2; an SBM local buy with no recorded
CBOT/FX falls back to history, renders gray/italic, and uses its own
1.1023 factor (shared B2 when the brief is SBM-only, embedded literal in
mixed "ALL" briefs) — in both Finance Brief and Period Brief. No
exceptions, and the existing import-contract and FX-impact sections are
unaffected (column positions in the Local Purchases table shifted, so the
Period Summary's "Local volume/value" formula reference was updated to
match).

## Unreleased — Fix: unrealistic CBOT Equivalent on non-CORN / zero-premium rows

Found by inspecting a real exported Finance Brief for SBM: the "CBOT
Equivalent (Implied)" column swung wildly (e.g. 292 vs 393 on deals days
apart) whenever a contract's own premium field was 0. Root cause was two
separate bugs in `export_finance_brief` and `export_periodic_brief`:

- The Assumptions sheet's conversion-factor cell was hardcoded to the CORN
  factor (0.3937) and labelled "CORN conversion factor" even when the whole
  brief was filtered to a different commodity (e.g. SBM, whose real factor
  is 1.1023). Fixed: when a brief is filtered to one commodity, the
  Assumptions cell now shows and uses *that* commodity's own factor,
  correctly labelled; mixed "ALL" briefs keep the CORN-only cell as before
  and other commodities embed their own factor directly in their row
  formula (this also means Market Premium is no longer silently blank for
  every non-CORN row — it used to only compute for CORN).
- A contract's premium field of 0 almost always means "not tracked for
  this deal," not "the true basis was zero" — but the formula
  (`CBOT = CIF ÷ factor − premium`) was using it as-is, which attributes
  the deal's entire CIF to CBOT and produces an inflated, unrealistic
  number. Fixed: when a row's own premium is 0/blank, the formula now
  falls back to that row's Market Premium (already computed elsewhere in
  the same brief from logged local price + CBOT history) instead, and the
  cell is colored orange with a legend note so it reads as an estimate,
  not a recorded deal term. CIF itself is unchanged — it still only
  re-derives from Avr CBOT + premium for CORN rows, same as before.

Verified headlessly against data shaped like the real uploaded file: a
0-premium SBM row that previously implied CBOT ≈ 393 now falls back to
Market Premium and lands at ≈ 300, in line with the period's own average
CBOT (307.2) instead of ~85 points off; a real-premium row is unaffected
and still uses its own premium. Confirmed the mixed "ALL" brief path keeps
CORN rows byte-for-byte identical to before. No exceptions in either path.

## Unreleased — Contracts tab: commodity filters, CBOT equivalent, formula-based stress, transparency

- **Period Brief & Finance Brief**: both exports now let you pick a single
  commodity (or "ALL") before generating, via a new dropdown in the export
  dialog. Sheet titles and the "no purchases found" message reflect the
  chosen scope.
- **CBOT Equivalent (Implied)** column added to both briefs: for every corn
  row with a known CIF and premium, computes
  `CBOT = CIF / 0.3937 − Premium` as a live Excel formula referencing the
  new Assumptions conversion-factor cell, so it recalculates if CIF/premium
  are edited in Excel. Sanity-checked against the user's own example
  (CIF=285, Premium=210 → CBOT ≈ 513.90).
- **Stress Scenario Excel** (`export_stress_excel`) rewritten to be fully
  formula-based: an Assumptions sheet holds editable CBOT, FX, premium,
  quantity, local price, fees and conversion-factor cells, and every
  Best/Base/Adverse case, the new "Δ Saving vs Base %" column, and the full
  shock-grid table are live formulas referencing those cells — change an
  assumption in Excel and every case and grid cell recalculates. Fixed a
  bug (caught in testing before release) where the Best row's Δ% formula
  referenced the Base row's cell before it had been assigned.
- **Analysis → Contract Performance → Contract Intelligence**: fixed the
  "🔬 Export Full Contract Intelligence" button doing nothing when clicked.
  Root cause was a `NameError` from a stale variable reference that Tkinter
  silently swallowed, so the button was never actually created after
  selecting a contract. Also fixed the detail panel destroying and
  recreating its button row on each selection instead of stacking widgets.
  Local price window: confirmed this is anchored per-contract to that
  contract's own delivery date (all local prices on/after delivery date,
  unbounded) unless you narrow it with the optional From/To fields — it is
  not a single fixed window shared across contracts.
- **Supplier Scoreboard**: added an "Avg CBOT" column (distinct from "Avg
  CBOT Edge ¢"), computed from each contract's final pricing CIF and
  premium the same way the rest of the app derives implied CBOT — reflects
  final pricing/premium, not a live quote. Also fixed a crash in the
  scoreboard's summary note when the top-ranked supplier had no CBOT-edge
  data yet.
- **Exposure & Risk → Portfolio Stress Test**: the result panel now shows
  the actual formula and plugged-in numbers behind the FX and CBOT impact
  figures (exposed USD × shock% × FX rate; and per-commodity CBOT × shock%
  × conversion factor × unpriced MT × FX rate), not just the final totals.
- **Local Purchases**: added an "⟳" button to auto-fill CBOT Ref / FX Ref
  from the nearest logged CBOT/FX history on or before the purchase date,
  and a new "Basis" column showing the implied basis for each purchase
  using the same formula as Basis Tracker.

Verified headlessly end-to-end (synthetic contracts, CBOT/FX/local history,
one local purchase): Period Brief CBOT-equivalent math matches the worked
example; Stress Excel exports with correct Best/Base/Adverse Δ% formulas
referencing the Base row; Contract Intelligence button now creates and
replaces correctly across repeated selections with no stacking; Supplier
Scoreboard runs and reports correctly whether or not CBOT-edge data exists;
Exposure & Risk shows the full formula breakdown; Local Purchases auto-fill
and Basis column compute correctly. No exceptions logged in any path.

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

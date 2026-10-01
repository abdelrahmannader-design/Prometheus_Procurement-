# 2026-10-01 (b) — Fix: yield shown as "final, +0.0%" during the season

- USDA also copies the latest forecast into the year's annual figure; the app now ignores that copy until it differs (the real final in January), so the card compares this month's forecast with last month's.

# 2026-10-01 — Market Signals: full USDA crop data + Wheat

- Your NASS key now also brings: planting/harvest progress (with last year and a 5-year average the app computes from USDA's last 5 seasons), yield & production forecasts (Crop Production), quarterly grain stocks, state-level crop condition for the main producing states, and the full excellent / good / fair / poor / very poor split.
- Three new signals in the bias: Crop progress, Yield forecast, Grain stocks (9 signals in total).
- New "USDA crop" view: season chart of % good/excellent vs last year, condition split bar, state table with weekly change, progress bars vs average, yield and production with change vs the previous forecast, and a stocks bar chart by quarter.
- Wheat added to Market Signals (CFTC, futures curve, USDA, history); the CBOT history now also stores Wheat (ZW=F).
- Each USDA part loads independently; a part that fails is named in the status line and the others still show.

# 2026-09-29 — CBOT history: 10-year backfill

- Setup & Data → FX & CBOT History: new "Backfill 10 years (seasonality)" button fetches up to 10 years of daily CBOT closes (Corn, Soybean, SBM) so Market Signals → Seasonality and the stress-test history have enough years to be meaningful. Existing closes are kept; only missing dates are added.

# 2026-09-28 — Market Signals redesigned (Aurora look)

- The Market Signals tab now uses the app's modern design kit, like the CBOT Desk:
  - Gradient header with the selected commodity's bias (swipe / arrows to switch CORN · SOYBEAN · SBM) and quick actions: Fetch latest, Use in stress test, CBOT targets. A coloured status dot shows whether the last fetch worked.
  - One card per commodity with a half-dial gauge (lower ← → higher risk), the bias chip, score, signals used and unpriced MT; click a card to select it.
  - Advice banner for the selected commodity with one-click stress-test shocks.
  - One card per signal (icon, lean chip, reading, why it matters, source, date, weight dots); sources not yet in use show a "not used yet" card saying how to add them.
  - Report calendar as a timeline grouped by week with date badges, impact chips and a ✕ to hide; a banner for the next high-impact report and your unpriced MT.
  - Seasonality as a bar chart (red = months CBOT usually rose, green = fell, purple = next month) with the share of up-years per month.
  - Settings: NASS key and WASDE numbers in their own cards.
- The classic table layout is kept automatically if the modern kit is unavailable.

# 2026-09-27 (m) — Approvals & Change History

- New Contracts → Approvals & History tab.
- **Approvals**: request approval for an import contract or a local purchase. The request freezes the key terms and shows the approver quantity, CIF / landed cost, saving vs local and vs budget. Approve / Reject (with comment) / Withdraw. Optional approver PIN (stored hashed). If a key term (qty, CIF, premium, supplier, dates, FX, fees / price) is edited after the request, it shows "⚠ Changed after request" and raises a High alert; waiting requests raise a Medium alert.
- **Change history**: every save logs field-level changes to contracts, local purchases, local prices and budgets — when, who, record, field, old → new — plus approval requests/decisions and data restores. Filter, search and export to Excel. The app's own start-up clean-ups are not logged as user edits.
- "Your name" setting (defaults to the Windows user name) is used in history and approvals.
- Engine: `prometheus_core/history.py`, tests in `tests/test_history.py`.

# 2026-09-27 (l) — Excel Import Center

- Setup & Data → Imports: **Download import template** (one workbook, a sheet each for Contracts, Local Purchases, Local Prices, Budgets, FX History, CBOT History; required columns marked *, drop-down lists for choices, help + example in row 2).
- **Import from Excel…**: every row is checked and shown first — NEW / UPDATE (with the changed fields) / SAME (already saved) / ERROR (with the reason) / DUPLICATE — nothing is saved until you press Import. A backup is made first; each import is written to the audit log.
- Matching: contracts by contract_id, else name + supplier + commodity (only filled cells are changed); local purchases by date + commodity + supplier + qty + price; local prices by date + commodity; budgets by commodity + year; FX by date; CBOT by date + commodity. Dates accept YYYY-MM-DD, DD/MM/YYYY or Excel dates.
- Engine: `prometheus_core/importer.py`, tests in `tests/test_importer.py`.

# 2026-09-27 (k) — Budget vs Actual in USD/MT (CIF or delivered)

- Each budget line now has a **currency (USD / EGP)** and a **basis (CIF / DELIVERED)**; default USD CIF. Budgets saved earlier stay EGP delivered.
- Costs are compared on the same basis: imports use the contract CIF (or landed ÷ contract FX); local purchases use price + transport, or their CIF-equivalent (minus average import fees), converted with the FX on the purchase date.
- "Market today" follows the basis: live CBOT + latest premium for CIF, today's local price for delivered.
- USD figures show 2 decimals; unit column in the app, Excel and Monthly Report; a warning if a USD price looks like EGP (or the reverse).

# 2026-09-27 (j) — Budget vs Actual

- New Analysis → Budget vs Actual tab. Enter a budget EGP/MT (and optional budget MT) per commodity for this year and next; calendar or fiscal year ("Year starts in").
- Per commodity: bought MT (actual + committed), average paid, vs budget per MT and in EGP, MT left to buy, the maximum EGP/MT the rest can cost to still land on budget, today's local price and the full-year forecast.
- Detail list of every purchase counted (closed imports, open imports with unpriced MT at live market, local purchases) with its own vs-budget figure.
- Alerts in the Action Centre, a table in the Monthly Report PDF, and a formula-based Excel export (also in the Export Center / CEO digest).
- Engine: `prometheus_core/budget.py`, tests in `tests/test_budget.py`.

# 2026-09-27 (i) — Market Signals: faster fetch with live progress

- All sources (CFTC ×3, futures curve ×3, USDA) are now fetched in parallel, so the wait is the slowest source, not the sum.
- The status line shows live progress per source (… / ✔ / ✖) and the seconds elapsed; pressing Fetch while a fetch runs shows its progress instead of doing nothing.
- "Save key" saves and fetches straight away; a key typed but not saved is also used by Fetch.
- Signals table is compact so the WASDE box and buttons sit right under it; double-click a signal to read it in full.

# 2026-09-27 (h) — Market Signals: which way is the CBOT risk leaning?

- New Analysis → Market Signals tab with three views.
- **Signals & bias** per commodity (Corn, Soybean, SBM): CFTC fund positioning (fetched automatically, no login), USDA NASS crop condition (free API key, saved in the app), USDA WASDE ending stocks (typed after each monthly report), CBOT futures curve (front vs ~5 months out), price trend (50/200-day) and seasonality from the app's CBOT history. Each signal shows its reading, why it matters, source and date; the bias is the weighted vote — a risk lean, not a price forecast. Missing sources are listed as "not used" with what to do.
- "Use this bias in the stress test" writes matching CBOT shocks into the Calculate stress settings.
- **Report calendar**: next 60 days of WASDE (estimated dates), Crop Progress, Grain Stocks, Prospective Plantings/Acreage, Export Sales and COT, plus your own events (add / hide / delete). Action Centre alert the day before a High-impact report when MT is unpriced, and when the bias leans UP on a commodity with unpriced MT.
- **CBOT seasonality** table by calendar month (average change, % of years higher), next month highlighted.
- Data is fetched in the background when the tab is first opened each day or with ⟳ Fetch latest; if a source cannot be reached the tab says which one and keeps the last saved values.
- Engine in `prometheus_core/market_signals.py`, tests in `tests/test_market_signals.py`.

# 2026-09-27 (g) — CBOT Targets for unpriced quantity

- New Contracts → CBOT Targets tab: set BUY BELOW levels (price when CBOT falls there) and PROTECT ABOVE caps (price anyway if CBOT rises there), each with a quantity, on any open contract with unpriced tonnage. "Suggest a ladder" splits the unpriced MT into three levels (−2/−4/−6 % vs live) plus a +5 % cap.
- Live status per target (HIT / Near within x % / Waiting / Done), distance to the level and the saving per MT the target would lock in (shared savings engine).
- HIT → High alert, Near → Medium alert in Home's Action Centre and Exposure & Risk.
- "Record as pricing lot" stores the fixed CBOT as a pricing lot (today, target qty, contract premium) and closes the target; the contract's unpriced quantity drops accordingly.

# 2026-09-27 (f) — Stock Cover & Buying Plan

- New Analysis tab: per commodity, stock today (FIFO) + open contracts arriving on their delivery dates − daily use, projected day by day over a horizon (default 180 days). Shows cover days, the date stock drops below the safety level (default 15 days of use), the run-out date, the buy-by date (safety date − import lead time, default 45 days) and the quantity to buy. Open contracts without a delivery date are listed, not counted.
- Month-by-month projection per commodity; formula-based Excel export (edit use or arrivals and it recalculates).
- Home Action Centre / Exposure & Risk get a High alert when a purchase is due within 14 days or the lead time no longer fits; the Monthly Report gets a "Stock cover and buying plan" table.

# 2026-09-27 (e) — Offer Comparison: intake by supplier/origin, Direct + Indirect, live CIF

- Changing the supplier (or origin) now always refreshes the intake. Lookup uses the origin-specific key (CORN-BRZ, CORN-UKR…) then the base commodity; a supplier saved only under origin rows is found too, and a note shows which Setup row was used.
- Separate Direct intake and Indirect intake columns plus "Intake used" (DIRECT / INDIRECT) — only the chosen route is charged; the Excel export has the same columns and formula.
- CIF $/MT column computes automatically as soon as a premium (or flat CIF) is typed, and follows CBOT/commodity changes.

# 2026-09-27 (d) — Supplier Offer Comparison

- New tab Calculate → Offer Comparison: up to 6 offers (CBOT + premium or flat CIF), each with its own freight, intake, clearance, payment days, quality adjustment and quantity, priced on one shared CBOT / FX / interest rate / local price (⟳ fills them from the market).
- Ranked by landed cost = (CIF + finance carry) × FX + fees + quality adj., with saving vs local, gap vs the best offer, the price to negotiate to match the best offer, and the highest price that still beats local.
- Picking a supplier fills its intake (Setup → Suppliers) and the commodity freight default; offers are remembered.
- Formula-based Excel export (RANK, gaps and break-even prices are live formulas).

# 2026-09-27 (c) — Procurement Monthly Report (PDF)

- New one-click management report (Home → "Monthly Report (PDF)", Export Center, CEO email digest; included in the Executive Pack). Choose any of the last 24 months.
- Page 1: KPI tiles (realized this month, YTD, open book expected saving, unpriced/FX-open MT), a written summary, a 12-month realized-savings chart, realized savings by commodity (month and YTD).
- Page 2: best contracts closed and contracts that lost vs local, open position and risk by commodity, local purchases of the month with their verdicts, risk alerts, high-priority data gaps.
- Every figure comes from the shared savings engine (realized = Savings tab, open = Home live).

# 2026-09-27 (b) — Data Health: a fix list instead of an error count

- The status-bar / top-bar chip now counts real data fixes (High + Medium) found by scanning contracts, local purchases and market data — no longer the raw error log (e.g. repeated failed FX fetches).
- Data Health window, tab "What to fix": each row names the record, the problem, what it breaks and how to fix it; double-click opens the contract, local purchase or Setup screen. Filter by severity/area; export to Excel with Owner/Done columns.
- One-click fix for closed contracts that have a CIF but are not marked priced (they were silently excluded from the Savings total).
- Tab "Technical log": the old log, grouped so repeats show once, with Clear log.

# 2026-09-27 — One savings engine everywhere

- New `_contract_savings_economics`: closed contracts = Savings tab (saved CIF × delivery FX + resolved fees, local on/before delivery); open contracts = Home Open MTM (Live).
- Contract Detail, Supplier Scorecard and Seasonality no longer use raw freight (missing DETAILED VAT) or a local price up to 14 days after delivery. The local window now averages only earlier days.
- Contract Performance: card uses the resolver fees; delivery anchor = last price on/before delivery (shown as first row).
- Contract Intelligence export, Contracts table totals (no more corn-only 0.3937 live CIF), Local Purchases import KPIs, monthly import-parity fees and the savings narrative use the same fees.
- Portfolio Excel open sheet defaults to Home's Live figures; switches for contract CIF and Form 4 FX.
- Regression test: every screen returns the same saving per contract.

# 2026-09-24 (c) — Calculate: finance carry applies to contracts too

- With a contract selected, Finance Days and Interest Rate were ignored (carry forced to 0 to match Home). They now apply: Carry USD/MT = CIF × rate × days / 360 is added to Own-after, the saving and the stress test. Leave them at 0 to reconcile with Home/Portfolio; the status line states whether carry is included.

# 2026-09-24 (b) — Calculate: local price matches Home and Savings

- Selecting a contract in Calculate now always refreshes the Local Price (all-in, incl. local transport): open contracts use today's latest local price (same as Home, Live mode); closed contracts use the last price on/before delivery (same as the Savings tab). Previously the field was only refilled when the contract had a delivery date, so a previous deal's local price could stay in the field. The status line shows which price and date were used.

# 2026-09-24 — Stress Excel: complete best/adverse rows

- Best and Adverse rows on the Stress Test sheet now show CBOT, FX, premium, landed cost and the shocks used (they previously showed only saving and total). Best = lowest shock of each list, Adverse = highest; a check column confirms they equal the grid max/min.
- Premium shocks are editable cells (Assumptions row 15) that drive the grids.
- Note on the sheet: values appear once Excel calculates (click Enable Editing; previews and Protected View do not calculate).

# 2026-09-23 (b) — Stress test for flat-price deals

- Stress test and its Excel now work for flat-price deals (SFM, DDGS, fixed $/MT contracts): the flat CIF price is shocked with the CBOT/price % list and FX with the FX list. A contract with a saved price is fixed, so only FX is stressed. Previously these deals had no stress result and the export said "Run Calculate first".
- The export now states the real reason when a stress test is unavailable, and an aborted calculation no longer leaves the previous deal's stress result exportable.

# 2026-09-23 — Formula-based Portfolio, Local Purchase judgment, configurable stress test

**Contracts → CPG Portfolio Excel (rebuilt, formula-based)**
- Closed contracts reproduce the Savings tab exactly (same fees resolver, same local price on/before delivery). Previously the sheet used the nearest local price within ±15 days (could be after delivery), raw freight without VAT and the discharge field only.
- Open contracts now show the **CIF of the moment** = (live CBOT + premium) × factor, plus CIF used (priced part at contract/lot CIF, unpriced part live), FX used (Form 4 FX when secured, switchable), expected saving and pricing MTM.
- Assumptions sheet (FX, live CBOT per board, factors, latest local price per key, thresholds) drives every formula. New "How Savings Work" sheet.

**Local Purchases**
- CBOT Ref / FX Ref fill automatically from history on or before the purchase date (typed values are never overwritten; ⟳ refills). Saving without them resolves them from history.
- New judgment: import parity on the purchase date = (CBOT on date + premium reference) × factor × FX on date + import fees, and local market price on/before the date. Verdicts: source (local vs import), price (vs market) and overall. Replaces the comparison with contracts delivered ±45 days (priced at other dates) and the ±14-day market window that could look into the future.
- Table gains a Verdict column; KPI "Saving vs Import Parity". New local-purchases-only Excel (Local Purchases, Summary, Assumptions, How It Is Judged), all formula-based.

**Calculate → Stress test**
- CBOT and FX shock percentages are now user inputs (saved), replacing the fixed ±5%. Base (0%) always included. Home signals use the same settings.
- "Use CBOT history" builds CBOT shocks from the 12-month low/high and the worst move over a chosen horizon. Named history scenarios (12-month low/high, all-history low/high, worst/typical horizon moves) are shown with their saving.
- Stress Excel rebuilt: shock % cells on Assumptions drive every grid cell; best/adverse are MAX/MIN of the grids; break-even CBOT/FX are formulas; new "CBOT History Scenarios" sheet.
- Validation: 188 tests passed; generated workbooks recalculated in LibreOffice match the app's own figures.

# 2026-09-14 — Scenario CBOT vs local premium bridge

- Scenario Excel now calculates the current import premium implied by Scenario CIF, the local-equivalent CIF, the local-implied/break-even premium, and the premium gap versus local.
- Formula: `Implied Local Premium = ((Local All-In - Effective Freight - Selected Intake - Clearance) / Selected FX) / Conversion Factor - CBOT`.
- Cost Summary adds a dedicated `CBOT vs LOCAL — PREMIUM EQUIVALENT` block while the detailed Scenario Lab tab keeps the auditable formulas.
- This is the same non-SBM algebra used by Basis Tracker when its editable Expenses assumption equals the Scenario import cost stack and the same FX/CBOT references are used.
- Validation: 169 tests passed, 15 skipped; main module compiles successfully.

# 2026-09-13 — Contract freight / Scenario reconciliation

- Scenario Lab now sources import freight/transport from the actual remaining FIFO contract(s), including saved freight mode and VAT, before falling back to commodity defaults.
- Replacement-cost calculations use the same contract freight source, preventing Scenario Excel from using 323.13 when contract 460/20048300 stores 425.53 base / 485.1042 effective.
- Scenario Excel now includes a Freight Source line for auditability.
- Direct/Indirect Intake remains alternative-route logic; Clearance remains a separate contract fee.

## 2026-09-13 — Intake / Clearance separation hotfix

- Corrected the cost model so Supplier Direct Intake and Supplier Indirect Intake are alternative intake routes, never cumulative charges on the same quantity.
- Added a per-contract Intake Type (`DIRECT` / `INDIRECT`). Only the selected supplier intake rate is charged.
- Clearance is now a separate contract fee and is sourced from the contract's `clearance_egp_mt`; Supplier Indirect Intake is never used as a Clearance fallback.
- Contracts supplier autofill now updates only the selected intake/discharge field and leaves the contract Clearance unchanged.
- Scenario Lab and its Excel export now expose Intake Type, Direct Intake rate, Indirect Intake rate, Selected Intake, and Clearance separately. `Other Import Fees = Selected Intake + Clearance`.
- Inventory vs Market Excel now exposes historical and replacement intake mode/rates, selected intake, clearance, freight, and total expenses in separate columns.
- Calculate contract reconciliation, FIFO/replacement economics, stress/decision logic, and snapshots now use `Freight + Selected Intake + Clearance`.
- Regression coverage includes ADM Medsofts CORN: Direct 245.63, Indirect 320.87, DIRECT selected, Clearance 200.00 => chargeable intake/clearance 445.63 EGP/MT before freight; Direct and Indirect are not added together.
- Validation: 150 tests passed, 15 skipped; main module compiles successfully.

## 2026-09-13 — Inventory vs Market full expense breakdown hotfix

- Inventory vs Market Excel now exposes historical FIFO CIF, locked FX, freight base, VAT, freight incl. VAT, selected intake/discharge, clearance, and total FIFO expenses as separate numeric columns.
- Today's import replacement section now exposes CBOT, premium, conversion factor, replacement CIF, FX, freight base/VAT, Direct/Indirect Intake, total replacement expenses and a simple formula cost check.
- Local purchase base price and transport are shown separately.
- Excel audit formulas use direct multiplication/addition rather than nested IF formulas.

## V10.9.10 — Scenario Intake + Excel Simplicity Hotfix

- Scenario Lab replacement fees now use current Setup → Suppliers intake values first, weighted across remaining import FIFO layers; saved contract fees are fallback only.
- Superseded by the Intake / Clearance separation hotfix above: Direct and Indirect are alternative rates; the selected intake is combined with the contract's separate Clearance fee.
- Historical FIFO contract cost is not rewritten by the supplier master; only current replacement/scenario economics use current supplier intake assumptions.
- Scenario Excel now shows Direct Intake, Indirect Intake, Intake Type, and contract Clearance separately; only the selected intake is added to Clearance.
- Simplified Scenario Excel arithmetic: local all-in, import benchmark, saving/loss, total impact and edge formulas are direct + / - / × formulas. IF is retained only where the model must choose between alternatives (source, freight mode, CIF override, explicit consumption).
- Added regression tests for stale contract fee vs supplier setup reconciliation and simplified Scenario workbook formulas.

## V10.9.10 — Supplier Intake Autofill Hotfix

- Calculate: selecting a supplier now immediately loads its configured Direct and Indirect Intake for the selected commodity.
- Contracts: selecting a supplier now immediately fills the selected Direct/Indirect intake into the contract intake/discharge field; Clearance remains a separate contract value and is not overwritten.
- Commodity variants such as `CORN-BRZ` now resolve supplier defaults stored under base `CORN` (and vice versa when unambiguous).
- Changing supplier clears stale intake values when the new supplier has no configured defaults.
- Commodity changes fill blank supplier-fee fields without overwriting saved/manual contract overrides.

## V10.9.10 — Aurora Stress Reconciliation

- Fixed Deal Calculator vs Stress Test Base mismatch caused by finance carry being omitted from the stress engine.
- Stress landed cost now equals `(CIF + carry) × FX + direct intake`, matching the Single Deal Calculator direct-cost path.
- Finance Days and Annual Interest Rate are now passed from Calculate into Stress and Recommendation.
- Break-even FX and CBOT calculations now include the finance multiplier.
- Stress Excel Assumptions now includes Finance Days and Annual Interest Rate; all scenario formulas include finance carry.
- Added regression tests for the reported 4,000 MT CORN case: Base saving reconciles at `-220 EGP/MT`, with recommendation `Buy local`.
- Previous V10.9.9 source frozen under `legacy/V10_9_9_Aurora_FX_Exposure_Frozen.py`.

## V10.9.9 — Aurora FX Exposure

- Reworked FX coverage into an auditable contract-level exposure breakdown.
- CEO portfolio headline shows FX secured MT, FX floating MT, rounded coverage %, floating-contract count, and uncovered references.
- Each commodity CEO page now separates CBOT-unpriced exposure from FX-secured / FX-floating exposure.
- Open contracts remain in FX exposure regardless of delivery-date timing; closed contracts are excluded.
- Home Executive Summary renamed FX Hedge Coverage to FX Secured and now shows the floating quantity beneath it.
- Added regression tests for the 11,000 / 12,000 MT = 91.67% (displayed 92%) example and per-commodity FX breakdown.

## V10.9.8 — Aurora Open Unpriced Exposure

- Added explicit contract Pricing Status control: Unpriced / Partially Priced / Priced.
- Open unpriced quantity is now calculated independently from delivery date and physical FIFO status.
- Added Contracts Pricing filter and Open Unpriced KPI.
- CEO Brief Pipeline / Price Exposure now shows Open Contracted, Open Unpriced Exposure, and Future-Dated Inbound separately.
- Portfolio exposure now uses quantified pricing-lot splits where available.
- Kept backward compatibility with legacy `priced` and CIF fields.

# Changelog

## V10.9.6 — Aurora Executive FIFO

- Built on the user-attached V10.9.2 Aurora Interface 996 package; Aurora design retained.
- Rebuilt **FIFO Excel** as a formula-driven management workbook with FIFO Summary, FIFO Layers and Assumptions sheets, editable assumptions, weighted formulas, conditional formatting, filters, frozen panes and charts.
- Rebuilt **Scenario Lab Excel** with formula-driven scenario economics, editable CBOT/FX/premium/local/freight/VAT/purchase/consumption inputs, charting and a Current FIFO Sources audit sheet.
- Added **Local Purchases to FIFO** as received lots at local purchase all-in cost (price + transport), depleted in chronological FIFO with import lots.
- Added Local Purchase awareness to **Scenario Lab**, including Import vs Local FIFO mix and proposed purchase source selection (IMPORT / CBOT or LOCAL PURCHASE).
- Fixed the supplied **Calculate viewport clipping** by removing the legacy nested scrolling canvas and using Aurora's page-level scroll owner.
- Improved FIFO / Inventory vs Market wide-table usability with horizontal scrolling plus Executive / Full Audit column modes.
- Rebuilt **CEO Brief** as a portfolio page plus commodity-by-commodity decision pages covering stock, cost, local edge, replacement economics, coverage, FIFO age, inbound/unpriced exposure, realised context and data-quality warnings.
- Added **Analysis → CEO Email Digest** with selectable export catalog, Select All / Clear / Executive Pack presets, and Grouped vs Separate email workflows.
- Added teardown protection for Aurora KPI auto-fit callbacks during theme/navigation rebuilds.
- Preserved existing state compatibility and frozen attached V10.9.2 source.
- Validation: 144/144 automated tests pass under a virtual Tk display.

## Unreleased — Aurora: the modern interface

The app's chrome has been rebuilt around a modern design system, and the
CBOT workflow now has a screen of its own. Nothing about the calculations,
the saved state file or the exports changed.

**New `prometheus_ui` package** — a dependency-free Tk design system
(`theme`, `primitives`, `widgets`, `charts`, `ttk_skin`, `shell`,
`cbot_console`). Tk has no rounded rectangles, gradients or alpha channel,
so those are reconstructed from polygons, per-scanline corner insets and
pre-blended colours. One token set drives everything; screens are not
allowed to hardcode a hex value.

**New navigation shell** — a left rail with grouped destinations, badges
and a collapse toggle, a top bar carrying the page title, live FX/CBOT/data
-quality chips and a jump box, and a `Ctrl+K` command palette. The rail
drives the existing notebook, whose own tab strip is hidden by style — so
every existing screen keeps the parent it was written against and behaves
exactly as before.

**New screen: CBOT Command Center** (first destination on the rail). One
place to look before pricing anything:

- a live hero with the selected board, its 30-day move and quote age;
- stat tiles for board price, indicative EGP/MT replacement cost, unpriced
  tons and USD/EGP, each with its own sparkline;
- board history for CORN / SBM / SOYBEAN / WHEAT over 30D / 90D / 6M / 1Y /
  All, with a hover crosshair readout;
- price cover: the open book split priced vs unpriced, plus FX-unsecured
  value;
- where today's board sits inside the stored 12-month band, and the
  goods-only gap between CBOT-implied and local all-in;
- open price risk, unpriced tons and nearest delivery first, clickable
  through to the contract;
- signals: stale quotes, tons unpriced inside the alert window, FX not yet
  secured, and large 30-day board moves.

The screen's data layer (`CBOTFeed`) is pure Python over the existing state
file and is unit-tested head-less. It keeps the app's data-honesty rule: a
missing premium or quote is reported as missing, never treated as zero — a
replacement cost computed without a defensible premium is labelled flat
(zero basis) rather than presented as an estimate.

**Every existing screen modernises with it.** The token set is applied to
ttk itself, so tables, forms, buttons, combo boxes, notebooks and
scrollbars pick up the new palette, spacing and type scale without any
screen being rewritten.

**Day and Night themes**, switchable from the top bar or from
Setup & Data → Appearance, applied in place without a restart. The same
panel can switch the whole interface back to the classic tab bar; the
modern kit is also imported defensively, so a build without it still
starts.

Fixes found while doing this:

- The CEO Dashboard's two long header lines were centre-clipped at both
  ends on any window narrower than the text, losing the first word of each
  sentence. They are now left-anchored and wrapped to the live hero width.
- Analysis carries ten sub-tabs; notebook tab padding is tuned so all ten
  labels render in full instead of being truncated.

Tests: `tests/test_modern_ui.py` adds 50 tests — palette contrast (every
text/ground pair clears WCAG AA), gradient and rounded-corner geometry,
the full CBOT feed including its missing-data behaviour, widget and chart
smoke tests in both palettes (skipped where no display is available), and
source-level guarantees that navigation stays widget-identity based and
that the classic chrome remains reachable. Suite total: 123 tests.

## V10.9.2 — Remaining FIFO Inventory vs Current Local & CBOT

- Added **Analysis → Inventory vs Market**, a compact management table using FIFO remaining MT rather than original contract quantities.
- Default view is Open contracts; status filter supports All / Open / Closed while inventory membership still follows delivery + FIFO, not status.
- Each remaining layer shows historical FIFO cost, live CBOT, contract premium, explicit CBOT formula, current FX, current freight incl. 14% VAT, CBOT replacement cost, latest local all-in, edge vs local and edge vs replacement.
- Current replacement uses today's FX; historical FIFO cost stays frozen. Missing/zero premium does not silently become zero-basis — replacement is marked incomplete.
- Added quantity-weighted commodity subtotal rows and Excel export.
- Added Home and FIFO-detail shortcuts into Inventory vs Market.
- Added pure `inventory_market_layer_metrics()` business logic and regression tests.
- Preserved V10.9.1 as `legacy/V10_9_1_Frozen.py`.


## V10.9.1 — Daily FIFO Inventory + Scenario Lab

- Added a single auditable FIFO inventory engine shared by Home and Scenario Lab.
- Contract Open/Closed status no longer decides current inventory: delivered Open and Closed tons remain inventory until FIFO consumption removes them; future Open deliveries stay inbound/pipeline.
- Added physical-stock baseline reconciliation, oldest-first depletion, remaining-lot cost/value, oldest/newest remaining contract, coverage, and shortage/data warnings.
- Added automatic daily analytical depletion from the configured MT/day rate when actual post-baseline consumption is absent. Automatic rows are labelled ESTIMATED and never write invented consumption-log entries.
- Added Current FIFO Inventory to Home with weighted average cost, latest local all-in, Inventory Edge/MT, total Inventory Edge, inbound/unpriced pipeline and drill-down reconciliation.
- Added daily FIFO snapshots for trend/audit while the app is used.
- Added CBOT replacement comparison using current CBOT/FX and a quantity-weighted defensible premium from remaining inventory; missing premium remains an explicit data gap.
- Added freight modes: DETAILED (base + VAT, default 14%), ALL_IN (no second VAT), and LEGACY (historical value preserved).
- Added Analysis → Scenario Lab for temporary CBOT/FX/premium/local/freight/VAT/purchase/consumption what-if calculations, saved-scenario comparison and Excel export.
- Preserved historical realised-savings logic and existing JSON compatibility.
- Added regression tests for FIFO delivery/status behavior, physical baselines, daily estimated depletion, weighted costs, freight VAT/no-double-VAT and scenarios.

## Unreleased — Local Purchases CBOT Equivalent: date-matched Market Premium

User-asked follow-up: why net out a *period-average* import premium
instead of the Market Premium at the specific purchase date, the way the
Basis Tab already does? Switched to exactly that. For each Local
Purchases row, the premium netted out of "CBOT Equivalent (Implied)" is
now tiered:

1. **Date-matched Market Premium** (preferred): Basis Tracker's own
   Implied-Basis method — the nearest logged local price on/before that
   purchase's own date, converted to CBOT terms via that date's CBOT/FX,
   minus that date's CBOT. New "Market Price EGP/MT at port (date)" and
   "Market Premium (date, ¢/bu)" columns show the number, live-formula
   linked to CBOT Ref/FX/local-expenses so it's fully auditable.
2. **This period's average import premium** (orange): falls back here
   only when no local price history exists for that specific date.
3. **Zero** (red): falls back here only when neither a date-matched
   market premium nor any import contract to average is available — the
   figure is then a zero-basis upper bound, not an estimate.

Verified headlessly: a row with local price history on its date uses the
live date-matched formula; a row with an import contract for that
commodity but no price history that day falls back to the period average
(orange); a row with neither falls back to 0 (red). No exceptions, and
the earlier fix's real-file numbers (CORN ≈466 vs Avr CBOT ≈450) still
hold with the date-matched method available. Full regression suite
re-run clean.

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

## V10.9.7 — Aurora Inventory Table + Date Order
- Fixed Inventory vs Market Executive/Full Audit row mapping: Source, Ref, Supplier, Commodity, Origin, Status and Pricing now align with their headers.
- Added `Origin` to the Executive view so import/local provenance remains visible without switching to Full Audit.
- Added persistent date-order selectors to Local Prices, FX Daily History and CBOT Daily History.
- Supported orders: `Newest → Oldest` (default) and `Oldest → Newest`.
- Date ordering is display-only; it does not rewrite market-history records or financial calculations.

- 2026-09-13 Contract calculator reconciliation fix: selected contracts now use Portfolio/Open Contracts landed-cost basis (CIF×FX + discharge + clearance + effective freight), exclude finance carry in contract reconciliation mode, and feed the same all-in fees into stress/decision calculations.

## Scenario FX Source Fix — 2026-09-13
- Added Scenario Lab FX source selector: `FORM 4 LOCKED`, `CURRENT MARKET`, and `MANUAL / STRESS`.
- Remaining FIFO contract Form 4 FX is quantity-weighted when more than one contract remains.
- Scenario Reset prefers Form 4 locked FX when available; otherwise it uses current market FX.
- Contract `460/20048300` resolves to Form 4 FX `51.0000` from the supplied JSON, versus current market FX `51.3410`.
- Formula Scenario Excel now exposes FX Source, Current Market FX, Form 4 Locked FX, source contract(s), Manual/Stress FX, and a transparent selector formula.
- FX +/- stress buttons and direct FX editing switch the Scenario FX source to `MANUAL / STRESS`.

## Scenario Dual Excel Views Fix — 2026-09-13
- Formula Scenario Excel now exports a new first tab, `Cost Summary`, designed for presentation and review.
- `Cost Summary` separates Local Cost, Import Cost, Decision/Inventory and a simple Cost Formula Map.
- The existing `Scenario Lab` detailed formula model remains as the second tab and is unchanged as the calculation source of truth.
- `Current FIFO Sources` remains as the third tab for inventory auditability.
- The summary exposes CBOT, premium, conversion factor, CIF, FX source/current/Form 4/selected FX, freight input/source/mode/VAT/effective freight, intake type/direct/indirect/selected intake, clearance, import fees and landed import cost.
- Summary cells reference the detailed model instead of duplicating assumptions, preventing the two views from drifting apart.

# Prometheus — how each analysis works

Plain-language guide to the **📊 Analysis** tabs, plus the three areas changed on
2026-09-23 (Portfolio Excel, Local Purchases, Stress Test).

## The one formula everything is built on

| Term | Formula |
|---|---|
| **CIF** (USD/MT) | (CBOT + Premium) × Factor. Factor: Corn 0.3937, Soybean/Wheat 0.36745 (¢/bu → $/MT), SBM 1.1023 ($/short ton → $/MT) |
| **Own-after** (EGP/MT) | CIF × FX + Intake/Discharge + Clearance + Freight (effective; +VAT when the contract uses DETAILED freight) |
| **Local all-in** (EGP/MT) | Local price + local transport |
| **Saving** (EGP/MT) | Local all-in − Own-after. **Positive = importing was cheaper than buying locally** |
| **Total saving** (EGP) | Saving × quantity |

Intake is either Direct *or* Indirect (never both). Clearance is always a separate contract fee.

---

## Analysis tabs

### 1. Contract Performance
**Use it to** see how one contract looks against the local market over time, from delivery until today.

- Choose a contract (optionally set a date range) and run the analysis.
- Own-after is fixed (contract CIF × delivery FX + selected intake + clearance + freight).
- Each row is a local price logged on or after delivery: Saving = Local − Own-after, with a running average.
- **Delivery anchor** = the local price closest to the delivery date.
- **CBOT columns**: "Spot own-after" = what the same premium would cost at that day's CBOT. vs Spot > 0 means you priced cheaper than that day's market.
- Signal: ≥ 200 **Strong save**, 0–200 **Marginal**, < 0 **Local cheaper**.

### 2. Contract Detail
**Use it to** grade every contract on five dimensions in one table.

1. **Implied CBOT** = CIF ÷ factor − premium: the CBOT you effectively locked.
2. **CBOT window**
   - Closed contracts: compared with CBOT closes in the *N* days before delivery (default 90). Percentile in that range: ≤ 25% **CHEAP**, ≤ 50% **FAIR-LOW**, ≤ 75% **FAIR-HIGH**, else **EXPENSIVE**. Edge = window average − implied CBOT.
   - Open contracts: compared with today's CBOT.
3. **FX impact**: own-after at a reference FX (the average delivery FX of closed contracts, or one you type) minus actual own-after. Positive means FX helped you.
4. **Local edge**: local price closest to delivery within ±*N* days (default 14) − own-after. > 500 **STRONG WIN**, > 0 **WIN**, > −500 **MARGINAL**, else **LOSS**. Break-even FX = (Local − fees) ÷ CIF.
5. **Overall**: combines 2 and 4 (e.g. "CHEAP BUY / FX HURT", "PRICEY / LOCAL HELPED").

### 3. Supplier Scorecard
**Use it to** rank suppliers fairly.

- Closed contracts only, analysed as in Contract Detail.
- Ranked by **average CBOT edge (¢/bu)**, not total saving, because total saving rewards whoever sold the most tonnage.
- Also shows average implied CBOT, average premium, average vs local, and win rate (% of contracts that beat local).
- Grades: A+ (rank 1), A (edge > 0), B (> −10), C (> −30), D.

### 4. Seasonality
**Use it to** learn which delivery months have been cheap.

- Closed contracts grouped by delivery month.
- Shows average implied CBOT, average percentile in its CBOT window, average edge and average vs local.
- Percentile ≤ 35% **Historically cheap**, ≤ 65% **Fair**, above that expensive. The cheapest month is highlighted.

### 5. Origin Compare
**Use it to** decide between origins after adjusting for quality.

- Uses the **latest local price** of each origin key (Local Prices).
- Quality cost vs the reference origin = price × (fines % − reference fines %) + energy adjustment (default 200 EGP/MT).
- **Net gap** = (reference price − origin price) − quality cost:
  - ≥ 0 **JUSTIFIED** (cheaper even after quality)
  - ≥ −50 borderline
  - otherwise not worth it
- The best net gap is recommended.

### 6. Savings Tracker (realized savings — the official number)
**Use it to** report realized savings.

- Only **Closed** contracts that are marked priced are counted.
- Saving = the last local price logged **on or before** the delivery/storage date − own-after (contract CIF × delivery FX + resolved fees).
- Totals by month use the closed/realized date.
- Open contracts are listed for audit only. Their value lives in Home → Open MTM.
- The new Portfolio Excel reproduces this tab row by row.

### 7. Basis Tracker
**Use it to** compare the premium you agreed with the premium the local market implies.

- **Market implied basis** (each logged local price) = ((local all-in − expenses) ÷ FX) ÷ factor − CBOT, using CBOT/FX on or before that date. "Expenses" is an editable setting.
- **Contract basis** = agreed premium (flat-priced contracts are rebuilt from CIF).
- **Local purchase basis** is plotted on the same chart.
- **Spread** = contract basis − market implied basis. Negative = your contract basis was below what local prices implied, which is good.
- Reference date modes: pricing date, delivery date, or today (MTM).
- SBM uses an equivalent-price comparison (local price ÷ FX ÷ 1.1023) instead of a basis.

### 8. Exposure & Risk
**Use it to** see open risk at a glance.

- Open contracts only:
  - priced vs unpriced MT (open CBOT risk)
  - FX-unsecured value (no Form 4)
  - delivery ladder (< 7 days, 7–30 days, > 30 days, no date)
  - supplier concentration
- Alerts, High/Medium/Low (also sent to Home's Action Centre):
  - CBOT daily move above the threshold
  - FX above (or close to) a contract's break-even FX
  - unpriced or no Form 4 FX close to delivery
  - Form 4 FX vs pricing-date FX gap
  - one supplier holding too much open volume

### 9. Inventory vs Market
**Use it to** see whether the stock you already hold is cheap or expensive versus today.

- Uses remaining **FIFO layers** (imports + local purchases, consumed oldest first).
- For each layer:
  - **Edge vs Local** = today's local − FIFO cost
  - **Edge vs CBOT** = today's replacement cost − FIFO cost, where replacement = (today's CBOT + premium) × factor × FX + freight + intake + clearance
- Positive = what you hold is cheaper than buying again today.

### 10. Scenario Lab
**Use it to** run a what-if on a new purchase.

- Inputs:
  - the current FIFO stock and cost
  - quantity and source to buy (Import or Local)
  - CBOT, premium, FX (market or Form 4), freight mode/VAT, fees
  - a consumption horizon
- **Scenario saving** = alternative cost − purchase cost (positive = the chosen source is cheaper):
  - IMPORT is compared with local all-in
  - LOCAL is compared with the import parity
- Also shows the new average inventory cost, projected stock and days of coverage.
- Exports a formula-based workbook with a CBOT-vs-Local premium bridge.

### 11. CEO Email Digest
Not a calculation. It bundles the exports you select (PDF/Excel) and emails them over SMTP on demand or on a schedule. The numbers come from the tabs above.

---

## Areas changed on 2026-09-23

### Contracts → CPG Portfolio Excel (formula-based)

**Sheets**
- Summary
- Assumptions (FX, live CBOT per board, factors, latest local price per key, thresholds, Form 4 switch)
- Closed – Realized
- Open – Live MTM
- How Savings Work

**Closed contracts:** identical to the Savings Tracker.

**Open contracts:**
- **CIF of the moment** = (live CBOT + premium) × factor
- **CIF used** = priced part at the contract/lot CIF, unpriced part at the CIF of the moment
- **FX used** = Form 4 FX when secured (switchable), otherwise today's FX
- **Expected saving** = local today − own-after
- **Pricing MTM** = (CIF of the moment − contract CIF) × FX × priced share

**Why it differs from the old sheet:** the old sheet used a local price up to 15 days *after* delivery, raw freight without VAT, and showed no CIF for unpriced contracts.

**Difference from Home:** Home's Open MTM (live mode) re-prices *priced* open contracts at today's CBOT. The Excel keeps their contract CIF and reports the market difference separately as Pricing MTM.

### Local Purchases — how a local purchase is judged

Each purchase is judged **on its own date, with data available that day**.

1. **Source decision.** Local all-in vs import parity on that date.
   - Import parity = (CBOT on date + premium reference) × factor × FX on date + import fees (+ optional finance carry).
   - CBOT/FX come from history on or before the date and fill in automatically. A value you type is never overwritten.
   - Premium reference = the latest premium agreed on or before the date (contract pricing dates and pricing lots).
   - Import fees = the quantity-weighted fees of your contracts.
2. **Price quality.** Local all-in vs the last local market price logged on or before the date.
3. **Overall verdict**
   - **✘ POOR DECISION** if import was cheaper by more than the threshold (default 200 EGP/MT)
   - **✔ GOOD DECISION** if local was cheaper and not above market
   - otherwise **⚠ ACCEPTABLE**
   - SFM/DDGS (no CBOT) are judged on price only.

**Why the old method was inaccurate:** it compared each purchase with the *simple average* of import contracts delivered ±45 days around it (or all contracts). Those contracts were priced at other dates, CBOT and FX, so it measured old pricing decisions, not the alternative you had that day. Its ±14-day market window could also use prices logged after the purchase.

### Calculate → Stress Test

- **CBOT shocks %** and **FX shocks %** are typed by you (e.g. `-15, -5, 5, 15`) and saved. 0% (the base) is always included.
- **📈 Use CBOT history** sets the CBOT shocks from the 12-month low/high and the worst fall/rise seen over the *History horizon* (days).
- Named history scenarios are listed under the heatmap with their saving:
  - 12-month low/high
  - all-history low/high
  - worst horizon fall/rise
  - 5th/95th-percentile moves
- **Stress Excel**
  - The shock % cells on the Assumptions sheet drive every grid cell.
  - Best/adverse = MAX/MIN of the grids.
  - Break-even CBOT/FX are formulas.
  - A CBOT History Scenarios sheet combines each historical CBOT level with the worst FX shock.

---

## Inconsistencies found (not changed yet)

- **Contract Detail, Supplier Scorecard, Seasonality**
  - They build own-after from the raw `freight_egp_mt` and `discharge_egp_mt` fields, not the shared fee resolver, so DETAILED-mode freight VAT and supplier-intake fallbacks are missed.
  - They take the local price *closest* to delivery within ±14 days, which can be after delivery.
  - Their "vs local" figures can therefore differ from the Savings Tracker.
- **Contract Performance**
  - The contract card shows raw fees, while the table uses the resolver.
  - The delivery anchor can be a price after delivery.

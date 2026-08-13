# Changelog

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

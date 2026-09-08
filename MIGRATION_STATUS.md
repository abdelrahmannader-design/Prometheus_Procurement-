# Migration Status — V10.9.2

- Architecture remains the existing modular Tkinter desktop application.
- Existing `app_state.json` files remain backward compatible.
- No historical contract freight is automatically changed to add VAT.
- Old freight rows without explicit mode remain `LEGACY` until edited.
- New optional state keys are created safely when absent:
  - `fifo_inventory_daily`
  - `saved_scenarios`
  - `ui.inventory_auto_estimate_daily`
- Current inventory is now independent of Open/Closed status: delivered tons remain in FIFO until consumed.
- Future Open deliveries stay in inbound/pipeline and are not counted as current physical stock.
- Daily automatic depletion is analytical only when actual consumption is absent; it does not manufacture consumption-log records.
- A physical stock-count adjustment remains the authority for re-anchoring FIFO quantity.
- Realised historical savings formulas are not rewritten by this release.
- The latest uploaded V10.8.15 source is preserved under `legacy/V10_8_15_Latest_Upload_Frozen.py`.

## V10.9.2 inventory-market notes

No destructive state migration is required. The new view is calculated from existing contracts, FIFO consumption/physical-stock data, local prices and live market data. Existing `app_state.json` remains compatible.

CBOT replacement is intentionally incomplete when current CBOT, current FX, conversion factor, current freight, or a positive contract premium is unavailable. No missing premium is assumed to be zero.

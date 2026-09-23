# V10.9.10 migration status

- Based on V10.9.9 Aurora FX Exposure.
- Existing `app_state.json` remains compatible; no state migration is required.
- No financial history, contracts, FIFO records, FX history, CBOT history, or local prices are rewritten.
- Single Deal Calculator remains the economic source of truth for the zero-shock Stress Base.
- Stress/Recommendation now includes the same finance carry inputs as Calculate.
- V10.9.9 source is preserved under `legacy/`.

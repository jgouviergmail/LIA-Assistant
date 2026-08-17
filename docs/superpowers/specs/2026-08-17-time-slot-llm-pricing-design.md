# Time-Slot LLM Pricing (UTC Peak / Off-Peak) — Design Spec

- **Date**: 2026-08-17
- **Status**: Validated design, awaiting implementation plan
- **Driver**: DeepSeek now bills text models by UTC time-of-day (verified 2026-08-17 on api-docs.deepseek.com): peak windows **01:00–04:00** and **06:00–10:00 UTC**, all other hours off-peak at exactly **50%** of peak. LIA currently bills the peak rate 24/7 (active seed rows carry peak prices), so every off-peak call is over-costed — including on the demo instance, which runs `deepseek-v4-flash` for every LLM type.
- **Goal**: a generic, centralized time-slot pricing mechanism — any provider, any model, 1..n UTC windows — administrable from the existing LLM text-pricing admin UI. Flat pricing remains the default and is byte-for-byte unchanged.

## 1. Verified architecture facts (evidence)

| Fact | Evidence |
|---|---|
| Cost valuation converges on 2 chokepoints | Sync: `get_cached_cost_usd_eur` (`src/infrastructure/cache/pricing_cache.py:342`). Async: `AsyncPricingService.calculate_token_cost` / `_at_date` (`src/domains/llm/pricing_service.py:488/360`). |
| Costs are persisted **at call time**, never recomputed on the nominal path | `TokenUsageLog.cost_usd/cost_eur` "at time of call" (`src/domains/chat/models.py:40`); `calculate_total_cost_from_logs` has zero callers. |
| The instance daily spend ceiling (ADR-216) reads the call-time ledger | `InstanceBudgetService.record_run_summary` fed from the run summary in the same transaction (`src/domains/chat/service.py:1158-1163`). |
| Pricing rows are temporally versioned (deactivate old + insert new, `effective_from`) | `LLMModelService.update` (`src/domains/llm/service.py:235-262`). |
| Redis pricing blob has drop-and-rebuild on incompatible shape | `PricingCacheService.load_from_redis` catches `KeyError/TypeError/ValueError`, deletes the key, rebuilds from DB (`pricing_cache.py:293-304`). |
| "Historical" recompute callers actually pass `now(UTC)` | `reminder_notification.py:574` (`at_date=datetime.now(UTC)`), `business_metrics.py:417` (end of run). |
| No migration prices `deepseek-v4-*`; existing DBs got those rows via the admin UI | Checked all `alembic/versions/`; only `deepseek-chat`/`-reasoner` are inserted (2025_11_04_0001). |

Design-validation simulations (executed, all green): `[start, end)` UTC resolution incl. midnight wrap; full-day (1440-minute) equivalence of the two representations (base=off-peak + peak slots vs base=peak + off-peak slots); circular non-overlap validator; Redis blob compatibility in both deploy directions (old blob → new code: `time_slots` defaults to `None` = flat pricing; new blob → old worker: `TypeError` → existing drop-and-rebuild).

## 2. Data model

New nullable JSONB column on `llm_model_pricing`:

```
time_slots: list[TimeSlotPrice] | None
TimeSlotPrice = {
  "start_utc": "HH:MM",             # inclusive, UTC
  "end_utc":   "HH:MM",             # exclusive, UTC; end < start = wraps midnight
  "input_unit_price": Decimal >= 0,
  "cached_input_unit_price": Decimal >= 0 | null,
  "output_unit_price": Decimal >= 0
}
```

Semantics:

- Base price columns (existing) = the default tariff, applied to any minute not covered by a slot.
- `NULL` / `[]` = flat pricing — the current behavior, no data migration needed.
- Slots are only accepted when `pricing_unit == 'per_1m_tokens'` (scope: LLM text tariffs; extensible later).
- Validation at write time (Pydantic, 422 on violation): `HH:MM` format, zero-length slots rejected, pairwise non-overlap on the 1440-minute circle, prices ≥ 0.
- Slots travel with the temporally-versioned pricing row: a price update that does not mention `time_slots` inherits the current row's slots (same mechanic as `pricing_unit`); an update passing `time_slots: []` clears them (stored as `NULL`). The empty list — not `null` — is the clearing sentinel on the wire, because `LLMModelService.update` builds its change set with `model_dump(exclude_unset=True, exclude_none=True)` (`service.py:200`), which silently drops explicit nulls; the frontend always sends `[]` when the toggle is off. A dedicated service/router test pins this. Historical cost recompute (`calculate_token_cost_at_date`) therefore uses the slots of the row effective at that date.

Why not alternatives: a child table duplicates rows on every temporal version and adds joins on the hot path; multiple pricing rows per slot breaks the "one active row per model" invariant relied on by `get_active_model_price().first()`, the admin UI, and the demo `unbillable_model` guard.

## 3. Resolution logic (single implementation)

New pure module `src/domains/llm/pricing_time_slots.py`:

- Pydantic `TimeSlotPrice` schema + list validator (used by admin schemas AND cache deserialization).
- `resolve_unit_prices(base_prices, time_slots, at: datetime) -> (input, cached, output)`:
  `t = at.astimezone(UTC).time()`; first slot containing `t` wins (non-overlap makes order irrelevant); membership is `start <= t < end`, or `t >= start or t < end` when the slot wraps midnight; no slot → base prices.

Consumers:

- `get_cached_cost_usd_eur(..., at: datetime | None = None)` — defaults to `datetime.now(UTC)`; signature is backward compatible, all existing callers unchanged. `CachedModelPrice` gains `time_slots: list[dict] | None = None` (JSON round-trip test required per the serialization-pair systemic rule).
- `AsyncPricingService.calculate_token_cost` (uses `now(UTC)`) and `calculate_token_cost_at_date` (uses `at_date`) — both route through `resolve_unit_prices`. `ModelPrice` NamedTuple gains `time_slots` (3 construction sites, all in `pricing_service.py`).

Timing convention (documented approximation): a call is valued at the instant the cost is computed (call completion — the same instant persisted with the log). A call spanning a slot boundary is valued at its completion tariff. `business_metrics.py` values at end-of-run (Prometheus business metric, non-billing — accepted).

## 4. Admin API

- `ModelPriceCreate` / `ModelPriceUpdate` / `ModelPriceResponse` gain optional `time_slots`.
- `_PRICING_FIELDS` in `src/domains/llm/service.py` gains `time_slots`; the temporal-versioning insert copies `price_changes.get("time_slots", current.time_slots)`.
- JSONB write rule: the column is always assigned a **new** list built from the validated payload (never mutated in place).
- Audit log details gain `time_slots_count` (no raw prices beyond what is already logged).
- Cross-worker invalidation: unchanged — the existing `_invalidate_caches` / Pub/Sub path already propagates any pricing mutation.

## 5. Admin UI (`AdminLLMPricingSection` / `ModelPricingModal`)

- Toggle "time-based pricing (UTC)" — rendered only when `pricing_unit == 'per_1m_tokens'`; off = flat pricing (slots cleared on save).
- Dynamic slot editor: add/remove rows; each row = start HH:MM, end HH:MM (UTC), 3 price inputs. Helper text states times are UTC and shows the browser-local equivalent for orientation.
- Client-side mirror of the non-overlap/format validation for immediate feedback (server remains authoritative).
- Table: base prices stay displayed; a badge marks time-based models (tooltip: slot count).
- i18n: all new strings in the 6 locales, strict key parity.
- A11y per apps/web CLAUDE.md: labelled controls via the field primitives, keyboard add/remove, error states announced.

## 6. Data & environments

- `infrastructure/database/seeds/llm_pricing_seed.sql`: the INSERT stays a verbatim prod extraction (no `time_slots` column, NULL = flat); a dedicated idempotent UPDATE block at the end sets the official DeepSeek v4 windowed tariff (base = off-peak; 2 peak slots 01:00–04:00 and 06:00–10:00 UTC at 2x).
- **Amended during implementation**: the demo instance's database lives in tmpfs and is rebuilt from the seed bundle at every boot (`DEMO_INSTANCE.md`), so an admin-UI entry would NOT survive a restart there — the windowed tariff MUST ship in the seed for the demo to bill correctly. The demo's Redis has persistence disabled (`--save ""`), so the pricing cache rebuilds from the freshly seeded DB at each boot with no stale-blob window.
- **No data-backfill migration** on existing databases (owner decision 2026-08-17): prod prices were entered via the admin UI and are not overwritten by migration; the owner enters the DeepSeek slots through the admin UI in prod. The schema migration only adds the nullable column.
- Known divergence (accepted): Langfuse computes costs from its own internal model registry and will not reflect off-peak rates — already true today; `TokenUsageLog` remains the accounting truth.

## 7. Testing strategy

- Unit (backend): resolution function (boundaries, wrap, full-day equivalence, no-slot, tz-aware non-UTC input), validators (overlap incl. wrap, format, unit restriction), `CachedModelPrice`/`PricingCacheData` JSON round-trip with slots, `ModelPrice` construction sites, `calculate_token_cost`/`_at_date` slot selection, admin router create/update/inherit/clear paths, blob-incompatibility drop path.
- Unit (frontend): pure helpers (slot payload build/parse, validation mirror), modal behavior (toggle, add/remove, error display), accessible names EN+FR, table badge.
- Gates: `task lint`, `task test:backend:unit:fast`, `task test:frontend`, `task ci:fast`; `task db:migrate:replay-check` for the migration. Ratchets shrink-only, coverage floors untouched or raised.

## 8. Out of scope

- Audio (`per_audio_*`), image-generation and Google-API pricing (separate systems).
- Any automatic price fetching from provider APIs.
- Langfuse cost alignment.

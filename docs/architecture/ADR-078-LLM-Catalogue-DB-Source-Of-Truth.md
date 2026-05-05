# ADR-078: LLM Catalogue DB-Source-of-Truth

**Status**: ✅ IMPLEMENTED (2026-05-05)
**Author**: Claude Code (Opus 4.7)
**Supersedes (in part)**: ADR-026 (the catalogue **source**, not the selection strategy)
**Related**: ADR-040 (Database Migration Strategy), ADR-063 (Cross-Worker Cache Invalidation)

## Context

Until v1.18.x, the LLM catalogue (chat models + image models) was hardcoded
across three frozen Python data structures:

- `FALLBACK_PROFILES: dict[str, ModelProfile]` (~750 lines in
  `infrastructure/llm/model_profiles.py`) — capabilities for every known
  model: max input/output tokens, supports_tools, supports_structured_output,
  supports_strict_mode, supports_streaming, supports_vision,
  is_reasoning_model.
- `IMAGE_GENERATION_MODELS: dict` — quality/size options for image models.
- `REASONING_MODELS_PATTERN: re.Pattern` — regex compiled at import time
  to detect reasoning models from their name (used in three different call
  sites: admin frontend constraints, OpenAI Responses adapter, generic
  adapter prepare_provider_config).

Adding a new model required (i) a code change against
`model_profiles.py`, (ii) a release tag, (iii) a redeploy. Tuning a single
capability flag on an existing model (for example, disabling
`is_reasoning_model` on `gpt-5-mini` after observing real behavior)
required the same chain — and the regex-based detection silently bypassed
the capability flag at three call sites, so an admin's intent in the UI
was not respected at runtime.

The legacy `llm_model_pricing` table only stored prices, indexed by
`model_name` (a free-text column), with no foreign key, no capability
information, and no provider field. The image generation pricing table
had no `provider` column either.

**Question**: how do we make the catalogue editable at runtime, by
administrators, without redeploying — and propagate every change live to
every consumer (LangChain factory, agent constraints UI, image
preferences dropdowns) across all worker processes and all browser
sessions?

## Decision

**Persist the catalogue in the database**. Two tables become the
source of truth:

1. **`llm_models`** (new) — one row per distinct `model_name`, with:
   - `provider: LLMProviderEnum` (openai, anthropic, deepseek,
     perplexity, ollama, gemini, qwen) — replaces the regex provider
     inference;
   - 8 capability columns: `max_input_tokens`, `max_output_tokens`,
     `supports_tools`, `supports_structured_output`,
     `supports_strict_mode`, `supports_streaming`, `supports_vision`,
     `is_reasoning_model`;
   - `is_active: bool` for temporal versioning (deactivated rows
     preserve history without breaking pricing FK chains).
2. **`llm_model_pricing`** (refactored) — pricing rows now FK to
   `llm_models.id` with `ondelete=RESTRICT`. The legacy `model_name`
   column is dropped; pricing joins through the catalogue.
   `(model_id, effective_from)` is composite-unique — one rate per
   model per date.
3. **`image_generation_pricing`** (extended) — gains a NOT NULL
   `provider: LLMProviderEnum` column so image options can be grouped
   by provider on the same enum as text models.

The tables are populated at boot time into two singleton in-memory
caches:

- **`ModelCapabilitiesCache`** (`infrastructure/llm/model_capabilities_cache.py`)
  — `get(model_name)`, `is_reasoning_model(model_name)`, O(1) dict
  lookups.
- **`ImageOptionsCache`** (`domains/image_generation/options_cache.py`)
  — `QualityOption`, `SizeOption`, `ModelOptions` dataclasses grouped
  by provider.

Every consumer reads from the cache, never from `FALLBACK_PROFILES`
(which is deleted, ~750 lines).

## Consequences

### Positive

- **No redeploy to add or tune a model.** Admins do everything from
  the 14-field admin form (Modèle / Capacités / Tarification).
- **Single source of truth.** The same row drives the LangChain
  factory, the agent constraints UI, the image preferences dropdowns,
  and the cost tracker.
- **Live propagation across workers.** Every admin write triggers a
  Redis Pub/Sub publish on `cache:invalidate:model_capabilities` (or
  `cache:invalidate:image_generation_options`); every worker reloads
  in milliseconds. See ADR-063.
- **Live propagation across browser tabs.** A new React Context
  (`apps/web/src/lib/catalogue-invalidation-context.tsx`) emits
  `model_capabilities` / `image_generation_options` events after a
  successful admin write; sibling components (LLM Configuration,
  Image Generation Settings) refetch automatically — no page reload.
- **Capability flags become authoritative.** The
  `is_reasoning_model` toggle in the admin UI is now respected at
  runtime by every detection site. The regex is preserved as a fallback
  for brand-new models not yet in the catalogue.
- **Temporal versioning for free.** Setting `is_active=false` on a
  catalogue row preserves history (and the FK from pricing) without
  deletion.

### Negative

- **Boot dependency.** The factory now requires the cache to be
  populated before the first LLM call. Mitigated by loading both
  caches synchronously in the lifespan startup, before the router
  registers any route. A hard failure at boot is loud and
  reversible.
- **Regex fallback path.** For models inserted after a worker has
  booted and before the next Pub/Sub event, the legacy regex still
  decides whether the model is a reasoning model. The window is
  bounded to the publish latency (typically < 50 ms) and the
  fallback is documented at every detection site.

## Migration Strategy (3-step pattern, ADR-040)

To roll out without downtime against existing pricing data, the
migration is split into three Alembic revisions:

1. **`2026_05_05_0001-llm_models_schema.py`** — creates
   `llm_models`, adds nullable `provider` and `model_id` to
   `llm_model_pricing` and nullable `provider` to
   `image_generation_pricing`. Reversible.
2. **`2026_05_05_0002-llm_models_backfill.py`** — backfills 47 known
   models from a frozen `MODELS_DATA` list (preserves capability
   profiles from the deleted `FALLBACK_PROFILES`). Backfills
   `model_id` on existing pricing rows by joining on `model_name`,
   and `provider='openai'` on every existing image pricing row (the
   only provider with image models at the time of writing).
   Reversible.
3. **`2026_05_05_0003-llm_models_constraints.py`** — flips backfilled
   columns to NOT NULL, drops legacy `llm_model_pricing.model_name`,
   adds the composite unique constraint
   `(model_id, effective_from)`. Reversible.

The seeds (`infrastructure/database/seeds/llm_pricing_seed.sql` and
`image_generation_pricing_seed.sql`) are rewritten to match: chat
seed inserts 119 catalogue rows then pricing rows via
`INSERT … SELECT … JOIN llm_models ON model_name`; image seed
includes `provider='openai'::llm_provider_enum` on all 27 rows.

## Cross-Sibling Frontend Invalidation

Across the dashboard, the admin LLM Pricing form, the admin Image
Pricing form, the LLM Configuration section (per-agent constraints)
and the Image Generation Settings page (user preferences) are
mounted as **siblings** under the same provider tree but do not
share state. After a successful admin write, the form must signal
the consumer pages to refetch.

We had two viable patterns:

- **Window event bus** (`window.dispatchEvent`) — globally available,
  zero React boilerplate, but no precedent in the codebase, no type
  safety, and no tearing guarantees if multiple writers race.
- **React Context provider with typed events**
  (`CatalogueInvalidationProvider` + `useCatalogueInvalidator` /
  `useCatalogueInvalidationListener` hooks) — idiomatic, fully
  typed, fits naturally inside the existing `Providers` tree.

We chose the React Context. It is mounted once at the dashboard
layout level and the consumer hooks are colocated with the data
fetching hooks (`useLLMConfig`, `useImageGenerationOptions`).

## Reasoning-Model Detection Consolidation

Three call sites used to compile the same regex
(`REASONING_MODELS_PATTERN`) at import time to decide whether a
model was a reasoning model:

1. `AdminLLMConfigSection.getModelConstraints` (frontend constraints
   UI).
2. `responses_adapter._is_reasoning_model` (OpenAI Responses API
   provider adapter).
3. `adapter._prepare_provider_config` (generic provider adapter).

All three now consult `ModelCapabilitiesCache.is_reasoning_model()`
first, falling back to the regex only when the model is not yet in
the catalogue. The regex remains useful for brand-new models added
post-boot but before the next reload tick — an honest fallback, not
a parallel source of truth.

## How to Add a New Model

1. **Through the admin UI** (recommended for production) — open
   *Administration → Tarification LLM Texte → Ajouter*. Fill in the
   3-section modal (Modèle: provider + name; Capacités: 8 toggles +
   2 token caps; Tarification: input/cached/output prices +
   effective date). Save. The new model is live across all workers
   in milliseconds.
2. **Through SQL** (for seeds or migrations) — `INSERT INTO
   llm_models (...) VALUES (...)`, then a separate `INSERT INTO
   llm_model_pricing (...) SELECT ... FROM llm_models WHERE
   model_name = ...`. Run
   `ModelCapabilitiesCache.invalidate_and_reload()` (or restart the
   workers) to pick up the new row.

## References

- `apps/api/src/domains/llm/models.py` — SQLAlchemy models
- `apps/api/alembic/versions/2026_05_05_0001-…0003-…` — migrations
- `apps/api/src/infrastructure/llm/model_capabilities_cache.py` —
  chat capabilities cache
- `apps/api/src/domains/image_generation/options_cache.py` — image
  options cache
- `apps/web/src/lib/catalogue-invalidation-context.tsx` —
  cross-sibling frontend invalidation
- `apps/web/src/components/settings/AdminLLMPricingSection.tsx` —
  14-field admin form
- ADR-026 (LLM Model Selection Strategy) — selection strategy
  unchanged; only the catalogue **source** moves
- ADR-063 (Cross-Worker Cache Invalidation) — the Pub/Sub bus that
  carries the invalidation events

# Personal Journals (Carnets de Bord) — Technical Documentation

## Overview

Personal Journals give the AI assistant a living, evolving personality through operational notebooks. The assistant writes behavioral directives, observations, analyses and learnings using a dedicated analyst persona (decoupled from the conversational personality). These directives influence future responses and planning via semantic context injection. Preferred format: WHEN [context] → DO [action] (BECAUSE [observation]).

**Key distinction from memories**: Memories store factual data about the user (psychological profile). Journals store the assistant's own perspective and reflections.

## Architectural evolution

This document describes the journal in its current form, which combines:

- The original feature ([ADR-057](../architecture/ADR-057-Personal-Journals.md), 2026-03-19): single-level entries, semantic injection into response and planner.
- The analyst persona fix ([ADR-064](../architecture/ADR-064-Journal-Analyst-Persona.md), 2026-03-25): fixed persona decoupled from conversational personality, directive format, mandatory dedup at consolidation.
- The Gemini embeddings migration ([ADR-069](../architecture/ADR-069-Gemini-Embedding-Migration.md), 2026-04-09): switch to Gemini `gemini-embedding-001`, dual-vector strategy (content + keywords).
- **The stratified consciousness refactor** ([ADR-079](../architecture/ADR-079-Stratified-Journal-Consciousness.md), 2026-05-06): four abstraction levels, epistemic status, deferred self-evaluation T → T+1, ambient diffusion of the compiled portrait, three-lever user correction.
- **Write restraint + level-routed injection** ([ADR-088](../architecture/ADR-088-Journal-Restraint-And-Level-Routed-Injection.md), 2026-06-02): restraint-first extraction (default `[]`, explicit-signal grounding bar, generic capability prohibition, capped L0 release valve), de-pressured consolidation (conditional L2, no synthesis quota), operational injection restricted to **L1/L2** (L0/L3 excluded), and ReAct directive coherence.

The sections below reflect the post-ADR-088 state.

## Architecture

### Domain Structure

```
apps/api/src/domains/journals/
├── __init__.py              # Package docstring
├── constants.py             # Domain constants (entry limits, emoji maps)
├── models.py                # SQLAlchemy models (JournalEntry + 5 enums incl. JournalEntryLevel + JournalEntryConfidence)
├── schemas.py               # Pydantic schemas (API + internal LLM, UUID validation, ConsolidationParseResult)
├── repository.py            # Data access layer (CRUD + dual-vector semantic search with min_score)
├── service.py               # Business logic (CRUD + dual embedding + atomic counter increments + size tracking)
├── router.py                # FastAPI endpoints (CRUD + settings + export + consolidate + portrait)
├── extraction_service.py    # Background extraction (ADR-079: previous-turn directives + inner-state section)
├── consolidation_service.py # Periodic maintenance + portrait compilation + level promotion (ADR-079)
├── context_builder.py       # Prompt injection via semantic relevance (with debug data)
├── portrait_builder.py      # Standalone build_journal_user_model_block (ADR-079, symmetric to build_psyche_prompt_block)
└── embedding.py             # Lazy-initialized GeminiRetrievalEmbeddings singleton (ADR-069)
```

### Database Schema

**Table: `journal_entries`**

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| user_id | UUID (FK→users) | Owner, CASCADE delete |
| theme | String(30) | self_reflection / user_observations / ideas_analyses / learnings |
| level | String(2) | L0 raw observation / L1 directive / L2 pattern / L3 portrait facet (default L1, ADR-079) |
| title | String(200) | Short descriptive title |
| content | Text | Full entry content |
| mood | String(20) | reflective / curious / satisfied / concerned / inspired |
| status | String(20) | active / archived |
| source | String(20) | conversation / consolidation / manual / user_correction (ADR-079) |
| session_id | String(100) | Conversation session that triggered extraction |
| personality_code | String(50) | Personality active when entry was written |
| char_count | Integer | Content character count (size tracking) |
| embedding | Vector(1536) | Gemini `gemini-embedding-001` (title + content) via pgvector HNSW |
| keyword_embedding | Vector(1536) | Gemini embedding of `search_hints` only (dual-vector match, ADR-069) |
| search_hints | String[] | LLM-generated keywords in user vocabulary for search bridging |
| confidence | String(10) | Epistemic status: low / medium / high (default medium, ADR-079) |
| evidence_count | Integer | Counter of confirmations from deferred self-evaluation (ADR-079) |
| contradiction_count | Integer | Counter of contradictions from deferred self-evaluation (ADR-079) |
| injection_count | Integer | Cumulative count of prompt injections (consolidation optimization) |
| last_injected_at | DateTime | Last injection timestamp (consolidation optimization) |
| created_at | DateTime | Auto-set |
| updated_at | DateTime | Auto-updated |

**User model additions** (13 + 3 portrait columns since ADR-079):
- `journals_enabled` (bool) — User feature toggle
- `journal_consolidation_enabled` (bool) — Periodic consolidation toggle
- `journal_consolidation_with_history` (bool) — Include conversation history
- `journal_max_total_chars` (int) — Max size limit (user-configurable)
- `journal_context_max_chars` (int) — Injection budget (user-configurable)
- `journal_max_entry_chars` (int) — Max chars per entry (user-configurable)
- `journal_context_max_results` (int) — Max search results (user-configurable)
- `journal_last_consolidated_at` (DateTime) — Last consolidation timestamp
- `journal_last_cost_*` (5 fields) — Last intervention cost tracking
- `journal_portrait_full` (Text NULL, ADR-079) — Compiled full portrait (~200 tokens)
- `journal_portrait_brief` (Text NULL, ADR-079) — Compiled brief portrait (~60 tokens)
- `journal_portrait_compiled_at` (DateTime NULL, ADR-079) — Last compilation timestamp

**Migrations**:
- `journals_001` — Creates `journal_entries` table + 11 initial user columns
- `journals_002` — Adds `journal_max_entry_chars` + `journal_context_max_results` (idempotent)
- `journal_search_hints_001` — Adds `search_hints` column (ARRAY(String(100)))
- `journal_pgvector_001` — Migrates embeddings to pgvector Vector(1536) with HNSW index; **destructive**: purges all existing entries
- `journal_injection_tracking_001` — Adds `injection_count` (Integer) and `last_injected_at` (DateTime) columns
- `journals_stratified_001` (2026-05-05, ADR-079) — Adds `confidence`, `evidence_count`, `contradiction_count`, `level` on `journal_entries` and `journal_portrait_full`, `journal_portrait_brief`, `journal_portrait_compiled_at` on `users`. All columns nullable or with server defaults — fully reversible without data loss.

### Stratification (ADR-079)

Each entry carries a `level` field that captures its abstraction depth:

| Level | Role | Created by |
|---|---|---|
| **L0** | Raw observation, pre-directive — open phrasing, ephemeral | Extraction (rare, when material is too ambiguous to formulate a directive) |
| **L1** | Operational directive — `WHEN [context] → DO [action] (BECAUSE [evidence])` | Extraction (default) |
| **L2** | Transversal pattern — synthesis of multiple convergent L1 directives | **Consolidation only** (active grouping by underlying topic) |
| **L3** | Portrait facet — traits, current phase, contexts, contradictions, blind spots, evolution | **Consolidation only** (alimentation du portrait) |

The default at extraction is L1. L0 is rare. L2 and L3 are exclusively produced/promoted at consolidation through active topic clustering (STEP 5 of `journal_consolidation_prompt.txt`).

### Epistemic status (ADR-079)

Three new fields on `journal_entries`:

- `confidence` ∈ {low, medium, high}: classifies the entry's status (untested hypothesis / default / validated). Set by the LLM at create or at consolidation; user-overridable via the API.
- `evidence_count` and `contradiction_count`: never written directly by the LLM. Incremented atomically by the service when the LLM signals an `evidence_outcome` on update actions (see deferred self-evaluation below). This eliminates hallucination risk on counter values.

### Data Flow

```
Conversation
    │
    ├── response_node.py ──┬── [INJECTION] build_journal_context(query=last_message)
    │                      │   → semantic search (min_score prefilter)
    │                      │   → {journal_context} in response prompt + injected_journal_ids in state
    │                      │   → ALSO: build_journal_user_model_block(format=full|brief)
    │                      │     → <UserModelContext> appended to base prompt (ADR-079)
    │                      │   → debug data → debug panel
    │                      │
    │                      └── [EXTRACTION] extract_journal_entry_background(previous_turn_injected_ids)
    │                          → fire-and-forget → LLM introspection
    │                          → reads PsycheState.last_appraisal (inner state section, ADR-079)
    │                          → reads previous-turn directives for deferred self-evaluation (T → T+1, ADR-079)
    │                          → create/update/delete entries with confidence + level + evidence_outcome
    │                          → UUID validation + hallucinated ID filtering (v1.8.1)
    │                          → debug results stored in _extraction_debug_results registry
    │
    ├── planner_node_v3.py ── [INJECTION] build_journal_context(query=goal+intent)
    │                          → semantic search (min_score prefilter)
    │                          → {journal_context} in planner prompt
    │                          → build_journal_user_model_block(format=full) appended (ADR-079)
    │
    ├── APScheduler (configurable) ── process_journal_consolidation()
    │                                  → batch eligible users → LLM consolidation
    │                                  → loads observed usage patterns (ADR-079, plain SQL)
    │                                  → MANDATORY dedup, reclassification audit, active stratification scan
    │                                  → compiles portrait_full + portrait_brief in same LLM call
    │                                  → persists portraits on users table
    │                                  → refreshes journal_zero_injection_age_days + journal_level_distribution gauges
    │
    ├── Manual triggers (ADR-079)
    │   ├── POST /journals/consolidate          — lever 3, same logic as scheduler
    │   └── POST /journals/portrait/feedback   — lever 2, creates user_correction L0 + sync re-consolidation
    │
    ├── Heartbeat (proactive) ── _fetch_journals + portrait brief
    │                              → second pass after context aggregation
    │                              → journal entries enrich notification context
    │                              → portrait brief in heartbeat prompt (ADR-079)
    │
    └── 6 secondary flows with ambient portrait brief (ADR-079)
        ├── react_setup_node       — <UserModelContext> SystemMessage
        ├── interests/proactive_task — interest content prompt
        ├── reminder_notification  — appended to system prompt
        ├── voice/service          — appended to voice prompt
        ├── heartbeat/prompts      — appended to heartbeat prompt
        └── fallback_response      — appended to fallback prompt (sync + async)
```

### Semantic Search & Prefiltering

- **Embeddings**: Gemini `gemini-embedding-001` (1536 dims, pgvector HNSW index) — ADR-069
- **Dual-vector strategy**: every entry has a `content` embedding (title + content) and a `keyword` embedding (search_hints only). Search picks `LEAST(dist_content, dist_keyword)` per row, bridging the gap between the assistant's introspective phrasing and the user's vocabulary.
- **Search hints**: LLM-generated keywords in user vocabulary, also embedded as a separate vector
- **Min score prefilter**: `JOURNAL_CONTEXT_MIN_SCORE` (default 0.63) — entries below this threshold are discarded BEFORE being sent to the LLM
- **Level routing (ADR-088)**: the operational chokepoint `build_journal_context` injects **only L1/L2 behavioural directives**. L0 (private feedstock) and L3 (carried by the compiled portrait) are excluded by default via `JOURNAL_OPERATIONAL_INJECTION_EXCLUDE_LEVELS = ["L0", "L3"]`. The repository methods (`search_by_relevance`, `get_recent_for_user`) take an optional `exclude_levels` param whose **default `None` preserves the all-levels view** — extraction and consolidation call the repository directly and still see every level.
- **Temporal continuity**: `JOURNAL_CONTEXT_RECENT_ENTRIES` most recent entries are always injected regardless of semantic score
- **Injection tracking**: Each injected entry increments `injection_count` and updates `last_injected_at` (fire-and-forget, non-blocking). These metrics are surfaced back to the LLM at extraction/consolidation as a self-feedback loop (ADR-079).
- **Dual injection**: Journal context is injected into both the **planner** (via `intelligence.original_query`) and the **response** (via `last_user_message`) prompts. Since ADR-088 the **ReAct reasoning loop** also receives L1/L2 directives, injected once at `react_setup` (count-capped by `JOURNAL_REACT_CONTEXT_MAX_ENTRIES`, full entries, no truncation) — closing the cross-mode gap. Deferred self-evaluation stays anchored to `response_node`.
- **LLM autonomy**: The LLM receives remaining entries WITH their similarity scores and decides which to use based on contextual relevance

### Configuration

**System (.env)**:
- `JOURNALS_ENABLED` — Global feature flag
- `JOURNAL_EXTRACTION_ENABLED` — Post-conversation extraction
- `JOURNAL_EXTRACTION_MIN_MESSAGES` — Min messages threshold (default: 4)
- `JOURNAL_CONSOLIDATION_INTERVAL_HOURS` — Scheduler interval (default: 4)
- `JOURNAL_CONSOLIDATION_COOLDOWN_HOURS` — Per-user cooldown (default: 12)
- `JOURNAL_CONSOLIDATION_MIN_ENTRIES` — Min entries for eligibility (default: 3)
- `JOURNAL_CONSOLIDATION_HISTORY_MAX_MESSAGES` — Max conversation messages for history analysis (default: 50)
- `JOURNAL_CONSOLIDATION_HISTORY_MAX_DAYS` — Max lookback days (default: 7)
- `JOURNAL_DEFAULT_MAX_TOTAL_CHARS` — Default max size (default: 40000)
- `JOURNAL_DEFAULT_CONTEXT_MAX_CHARS` — Default injection budget (default: 1500)
- `JOURNAL_MAX_ENTRY_CHARS` — Default max per entry (default: 800)
- `JOURNAL_CONTEXT_MAX_RESULTS` — Default max search results (default: 10)
- `JOURNAL_REACT_CONTEXT_MAX_ENTRIES` — Max L1/L2 directives injected into the ReAct reasoning loop, count cap with no truncation (default: 3; 0 disables, portrait only) — ADR-088
- `JOURNAL_CONTEXT_MIN_SCORE` — Min cosine similarity for prefiltering (default: 0.63)
- `NEXT_PUBLIC_JOURNAL_CONSOLIDATION_TIMEOUT_MS` — Frontend-side client timeout for the manual `/journals/consolidate` button (default: 240000 ms / 4 min, configurable to keep the loader visible long enough on heavy reasoning models)

**User (Settings > Features)**:
- Enable/disable journals (data preserved when disabled)
- Enable/disable periodic consolidation
- Enable/disable conversation history analysis (with cost warning)
- Max total chars (cannot be set below current usage)
- Context injection budget (chars injected into prompts)
- Max entry chars (cannot be set below largest existing entry)
- Max search results (entries returned by semantic search)
- All administered via `PATCH /journals/settings`

**Three corrective levers on the portrait (ADR-079)**:
1. **Lever 1 — edit L3 source entries**: standard CRUD via UI. Portrait recompiles on the next consolidation run.
2. **Lever 2 — flag (🚩 "Signaler un problème")**: free-text feedback → creates an L0 entry tagged `source=user_correction` → triggers a synchronous consolidation that re-weights L3 entries and recompiles the portrait with the user signal pinned at top of the prompt. Loader visible (~5–10 s on standard reasoning model).
3. **Lever 3 — manual recompile (🔄 "Consolider maintenant")**: bypasses the cooldown and runs the standard consolidation pass. Useful after a batch of edits or to refresh stale portraits.

The portrait itself is **never directly editable** — it is a synthesis. Users act through these levers; the synthesis stays coherent.

### LLM Configuration

Two entries in `LLM_DEFAULTS` + `LLM_TYPES_REGISTRY`:
- `journal_extraction` — Post-conversation (frequent, lightweight). Default: `openai/gpt-5.4-mini`, temp 0.5, reasoning_effort: low, power tier: MEDIUM. Reads the previous turn's injected directives + current `PsycheState.last_appraisal` to enrich the prompt with deferred self-evaluation context (ADR-079).
- `journal_consolidation` — Periodic review (rare, complex). Default: `qwen/qwen3.5-plus`, temp 0.5, reasoning_effort: low, power tier: HIGH. Same call now also compiles the user-model portrait (full ~200 tokens + brief ~60 tokens) — zero additional LLM call.

Both configurable in Admin > LLM Configuration (category: `background`).

### Heartbeat Integration

Personal Journals are integrated as a context source for proactive heartbeat notifications:

- **Source name**: `journals` — appears as a toggleable badge in heartbeat settings
- **Activation**: Badge is green when `journals_enabled=true`, grayed out when disabled
- **Dynamic query**: Unlike other sources fetched in parallel, journals use a **second pass** — after all other context is aggregated (calendar, weather, emails, tasks, interests), a dynamic query is built from the aggregated summary and used for semantic search
- **Budget**: Limited to 3 entries to keep the heartbeat prompt small
- **Prefiltering**: Same `JOURNAL_CONTEXT_MIN_SCORE` threshold applies
- **Prompt injection**: Journal entries appear as "ASSISTANT JOURNAL ENTRIES (your own reflections)" in the heartbeat context, allowing the assistant to personalize notification tone and content
- **Portrait brief (ADR-079)**: in addition to the dynamic-query entries, the heartbeat prompt now receives the compiled portrait brief (`<UserModelContext>` block, ~60 tokens). The notification voice is therefore aligned with the same user model used by conversation/planner.

### Dedup Discipline (ADR-064 → ADR-079)

The historical post-extraction merge guard (v1.12.1) has been retired. Deduplication is now handled in two places:

1. **Extraction prompt** — instructs the LLM to update an existing entry instead of creating a near-duplicate, surfacing the most recently used entries with their full IDs and metrics.
2. **Consolidation `STEP 1`** — explicit pairwise scan that merges semantic duplicates by emitting `update` (winner) + `delete` (loser) actions. The winning entry inherits search hints, the highest confidence, and the sum of evidence/contradiction counters.

Result: noise is collapsed periodically by an LLM that sees the full corpus, not opportunistically on every turn. No silent merge LLM, no orphan migrations, no `JOURNAL_DEDUP_SIMILARITY_THRESHOLD` to tune.

### Theme Selection (ADR-079)

The introspection prompt uses a discriminator-based decision tree:

- "Internal observation about my own behavior or evolution" → `self_reflection`
- "Stable signal observed about the user (preference, value, repeated context)" → `user_observations`
- "Cross-cutting pattern, hypothesis, or recurring contradiction worth analyzing" → `ideas_analyses`
- "Concrete lesson I can apply to do better next time" → `learnings`

Classification uses **discriminators**, not a theme distribution to balance: since [ADR-088](../architecture/ADR-088-Journal-Restraint-And-Level-Routed-Injection.md) the prompts no longer push the LLM toward "underrepresented" themes (that production pressure manufactured weak entries). The discriminators (e.g. a `BECAUSE` citing a past correction → `learnings`) are kept for correctness. Combined with the L0/L1/L2/L3 axis (see *Stratification* above), classification has two orthogonal dimensions: **what kind of insight** (theme) and **how distilled it is** (level).

### Anti-Hallucination Guards (v1.8.1, extended in ADR-079)

LLMs may hallucinate UUIDs and counter values when asked to update entries. Four layers prevent invalid operations:

1. **Prompt-level guidance**: Introspection and consolidation prompts include a CRITICAL instruction to copy-paste exact UUIDs from entry headers. Entry headers use `[id=UUID | ...]` format with a dedicated ID reference table for easy copy-paste.
2. **Schema validation**: `ExtractedJournalEntry.entry_id` has a `field_validator` that rejects malformed UUIDs (non-parseable strings). Invalid UUIDs raise `ValueError` and the action is skipped.
3. **Known-ID filtering**: Both `extraction_service.py` and `consolidation_service.py` filter out actions referencing entry IDs that do not exist in the loaded entries set. Actions with unknown IDs are logged as `journal_extraction_unknown_entry_id` / `journal_consolidation_unknown_entry_id` and silently dropped.
4. **Atomic counter increments (ADR-079)**: The LLM never writes absolute values for `evidence_count` / `contradiction_count`. It only signals an outcome (`evidence_outcome="evidence" | "contradiction"`) on update actions, and the service atomically increments the corresponding counter. Same pattern for level promotions: the LLM proposes a target `level`, the service emits `journal_consolidation_promotions_total{from_level,to_level}`.

### Debug Panel

The debug panel includes a "Personal Journals" section with two sub-sections:

**Context Injection** (reads):
- **Summary**: Entries found vs. injected, characters injected vs. budget, max results setting
- **Per-entry details**: Rank, theme emoji, title (25 chars), similarity score with visual bar, mood, source (conversation/consolidation/manual), date, char count
- **Budget indicator**: Entries that were found but not injected due to budget constraints are marked with a "BUDGET" badge and displayed at reduced opacity
- **Score legend**: Color-coded (green ≥0.70, yellow 0.50-0.69, red <0.50)

**Background Extraction** (writes, v1.8.1):
- **Summary**: Actions parsed from LLM output vs. actions applied (after UUID validation + filtering)
- **Per-action details**: Action type badge (CREATE/UPDATE/DELETE with color coding), theme emoji, title (30 chars), mood emoji, entry ID (8 chars for update/delete)
- **Timing**: Extraction results arrive via a separate `debug_metrics_update` SSE event after background tasks complete (post `await_run_id_tasks`), merged into the current debug state by the frontend

Data flows:
- **Injection**: `context_builder(include_debug=True)` → `state_update["journal_injection_debug"]` → `streaming_service` → SSE `debug_metrics` chunk → frontend
- **Extraction**: `extract_journal_entry_background()` → `_store_extraction_debug(run_id, data)` → `pop_extraction_debug(run_id)` in streaming service → SSE `debug_metrics_update` chunk → frontend `DEBUG_METRICS_UPDATE` reducer → merged into `JournalInjectionSection.tsx`

### Extraction Debug Registry

The extraction debug registry (`_extraction_debug_results` in `extraction_service.py`) is an in-process dict storing debug data keyed by `run_id`:

- **Write**: `_store_extraction_debug(run_id, data)` stores results with a monotonic timestamp
- **Read**: `pop_extraction_debug(run_id)` pops and returns results (single consumption)
- **TTL eviction**: Stale entries older than 5 minutes are evicted on each `pop_extraction_debug()` call to prevent unbounded memory growth when entries are never consumed (e.g., streaming error, debug panel disabled)
- **Error cleanup**: On extraction failure, the debug entry is removed to avoid orphaned data

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/journals` | List entries (filter by theme/level, pagination) |
| POST | `/journals` | Create entry manually (theme, level, confidence) |
| PATCH | `/journals/{id}` | Update entry (theme, level, confidence editable) |
| DELETE | `/journals/{id}` | Delete entry |
| DELETE | `/journals` | Delete all (GDPR) |
| GET | `/journals/themes` | Available themes |
| GET | `/journals/settings` | User settings + size/cost info |
| PATCH | `/journals/settings` | Update user settings |
| GET | `/journals/export` | Export JSON/CSV (entries + portrait, GDPR) |
| POST | `/journals/consolidate` | Manual trigger — runs the consolidation pass synchronously (lever 3) |
| GET | `/journals/portrait` | Read compiled portrait (full + brief + `compiled_at`) |
| POST | `/journals/portrait/feedback` | Submit a correction; creates an L0 `user_correction` entry and triggers consolidation (lever 2) |

## Prometheus Metrics (ADR-079)

Defined in `src/infrastructure/observability/metrics_journals.py`:

| Metric | Type | Labels | Purpose |
|--------|------|--------|---------|
| `journal_entries_total` | Counter | `action`, `theme`, `source` | Lifecycle volume per theme and source (conversation/consolidation/manual/user_correction) |
| `journal_extraction_duration_seconds` | Histogram | `outcome` | Latency of post-conversation extraction by outcome (success/parse_failed/error) |
| `journal_zero_injection_age_days` | Gauge | — | Average age of active entries that were never injected — central quality signal |
| `journal_evidence_total` | Counter | `outcome` | Deferred self-evaluation: `evidence` vs `contradiction` |
| `journal_consolidation_promotions_total` | Counter | `from_level`, `to_level` | Level transitions (L0↔L1, L1↔L2, L2↔L3) applied at consolidation |
| `journal_level_distribution` | Gauge | `level` | Active entries per level — sampled periodically |
| `journal_dedup_actions_total` | Counter | — | Dedup-induced deletes performed at consolidation STEP 1 |
| `journal_portrait_compile_duration_seconds` | Histogram | — | Cost of in-prompt portrait compilation |
| `journal_portrait_present_total` | Counter | `flow`, `format` | Where the portrait is injected (response/planner/react/voice/heartbeat/reminder/fallback/interest) and in which format (full/brief) |
| `journal_portrait_age_hours` | Gauge | — | Latest portrait age per user — surfaces stalled consolidations |
| `journal_portrait_feedback_total` | Counter | `outcome` | Lever-2 feedback events (success/error) |

These metrics underpin the dashboards used to verify that stratification is happening (level distribution evolves), self-evaluation is firing (`evidence_total` non-zero), and the portrait actually reaches secondary flows (`portrait_present_total{flow=...}`).

## Related ADRs

- [ADR-057: Personal Journals](../architecture/ADR-057-Personal-Journals.md) — Original feature
- [ADR-064: Journal Analyst Persona](../architecture/ADR-064-Journal-Analyst-Persona.md) — Persona and dedup discipline
- [ADR-069: Gemini Embedding Migration](../architecture/ADR-069-Gemini-Embedding-Migration.md) — Dual-vector search
- [ADR-079: Stratified Journal Consciousness](../architecture/ADR-079-Stratified-Journal-Consciousness.md) — Levels, epistemic status, deferred self-evaluation, portrait diffusion
- [ADR-088: Journal Restraint + Level-Routed Injection](../architecture/ADR-088-Journal-Restraint-And-Level-Routed-Injection.md) — Restraint-first write discipline, L1/L2-only operational injection, ReAct directive coherence

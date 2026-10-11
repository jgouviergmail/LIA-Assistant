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
- **Theme reachability** ([ADR-159](../architecture/ADR-159-Journal-Theme-Reachability.md), 2026-07-27): subject-based classification shared by both prompts, three grounding kinds (SAID / SHOWN twice / REACTED), removal of the consolidation ratchet that emptied `self_reflection`, correct theme on user-feedback entries, plus a CI reachability guard and a measurement harness. Restored per-theme recall from 1.00 / 0.58 / **0.00** / **0.00** to **1.00 across all four**, at unchanged noise (0.00).
- **The portrait reads four sources** ([ADR-292](../architecture/ADR-292-Portrait-Reads-Four-Sources.md), 2026-09-17): the consolidation prompt receives the long-term memories, the interests, the learned habits and the relationship debriefs — each offered through a seam (`domains/shared/portrait_sources.py`) so `journals` imports no source domain, read under its three gates, bounded by settings — and the portrait persists its PROVENANCE (`users.journal_portrait_sources`); a change in any source makes the account eligible again; the portrait's budgets are settings, never prose.

The sections below describe the current implementation, including the revision-bound evidence and safe consolidation amendment to ADR-079. Historical measurements above describe those decisions' original qualification, not a guarantee of current model quality.

## Architecture

### Domain Structure

```
apps/api/src/domains/journals/
├── __init__.py              # Package docstring
├── constants.py             # Domain constants (entry limits, emoji maps)
├── models.py                # SQLAlchemy models (JournalEntry + 5 enums incl. JournalEntryLevel + JournalEntryConfidence)
├── schemas.py               # Pydantic API/extraction schemas, UUID validation, provenance
├── repository.py            # Data access layer (CRUD + dual-vector semantic search with min_score)
├── service.py               # CRUD, prepared dual embeddings and versioned mutation delegates
├── evidence.py              # Owner/entry locks, fresh-rule updates, confidence clamp
├── evidence_models.py       # Idempotent evidence events tied to a rule revision
├── merging.py               # Explicit equivalent-rule merge and event/provenance union
├── lifecycle.py             # Corpus invalidation and portrait validity at read time
├── router.py                # FastAPI endpoints (CRUD + settings + export + consolidate + portrait)
├── extraction_service.py    # Background extraction (ADR-079: previous-turn directives + inner-state section)
├── extraction_context.py    # Visible human evidence and previous exposed revisions
├── extraction_actions.py    # Validated actions and short consent-fenced settlement
├── extraction_settlement.py # Provider preparation then atomic consent/owner-fenced extraction writes
├── consolidation_service.py # Bounded paid orchestration and attempt outcome
├── consolidation_lifecycle.py # Per-account lease, consent/source snapshot and work eligibility
├── consolidation_output.py  # Strict maintenance output and supported natural portrait claims
├── maintenance_actions.py   # Validate supports/merges, prepare embeddings, count actual mutations
├── consolidation_settlement.py # Prepared embeddings then one atomic maintenance/portrait transaction
├── portrait_sources.py      # Authorized source sections and provenance
├── portrait_review.py       # Independent bounded semantic review and publication receipt
├── source_state.py          # Source identities, gates, budgets and daily expiry
├── context_builder.py       # Prompt injection via semantic relevance (with debug data)
├── search.py                # The journal LOOKUP door (ADR-318): a subject embedded, L1-L3 above the configured floor
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
| embedding | Vector(1536) | Configured Gemini journal embedding of title + content via pgvector HNSW; model and output dimensions come from `src/core/config/journals.py` |
| keyword_embedding | Vector(1536) | Same configured embedding space for `search_hints` only (dual-vector match, ADR-069) |
| search_hints | String[] | LLM-generated keywords in user vocabulary for search bridging |
| confidence | String(10) | Epistemic status: low / medium / high (default medium, ADR-079) |
| evidence_count | Integer | Counter of confirmations from deferred self-evaluation (ADR-079) |
| contradiction_count | Integer | Counter of contradictions from deferred self-evaluation (ADR-079) |
| revision | BigInteger | Current rule proposition version; content replacement advances it and resets current-version counters |
| injection_count | Integer | Cumulative prompt exposures; not proof of correctness or usefulness |
| last_injected_at | DateTime | Last injection timestamp (consolidation optimization) |
| created_at | DateTime | Auto-set |
| updated_at | DateTime | Auto-updated |

**Table: `journal_evidence_events`**

Each row identifies one outcome by `journal_entry_id`, `rule_revision` and `event_key`; a unique index prevents a replay from qualifying the same rule twice. `outcome` accepts evidence or contradiction only, and the revision must be positive. The event belongs to a user and may retain an owned `source_conversation_id`; deleting that conversation clears its pointer, while account/entry deletion removes its events. See `evidence_models.py` for the complete registered schema. The account export and explicit account-purge registry include this table.

**User model additions**:
- `journals_enabled` (bool) — User feature toggle
- `journal_consolidation_enabled` (bool) — Periodic consolidation toggle
- `journal_consolidation_with_history` (bool) — Include conversation history
- `journal_max_total_chars` (int) — Max size limit (user-configurable)
- `journal_context_max_chars` (int) — Injection budget (user-configurable)
- `journal_max_entry_chars` (int) — Max chars per entry (user-configurable)
- `journal_context_max_results` (int) — Max search results (user-configurable)
- `journal_last_consolidated_at` (DateTime) — Source-read timestamp of the last successful settlement
- `journal_revision` / `journal_consolidated_revision` — Corpus work revision and last successfully consumed revision; deletions count even when no active entry remains
- `journal_last_attempted_at` / `journal_last_attempt_status` — Attempt pacing and outcome, independent of successful settlement
- `journal_consolidation_owner` / `journal_consolidation_held_until` — Expiring per-account lease shared by manual and scheduled runs
- `journal_last_cost_*` (5 fields) — Last intervention cost tracking
- `journal_portrait_full` / `journal_portrait_brief` (Text NULL, ADR-079) — Reviewed natural full synthesis and its brief essence
- `journal_portrait_compiled_at` (DateTime NULL, ADR-079) — Last compilation timestamp
- `journal_portrait_sources` (JSONB NULL) — Source counts/statuses, corpus revision, source/compiler fingerprint, supported claims and pending portrait work

**Migrations**:
- `journals_001` — Creates `journal_entries` table + 11 initial user columns
- `journals_002` — Adds `journal_max_entry_chars` + `journal_context_max_results` (idempotent)
- `journal_search_hints_001` — Adds `search_hints` column (ARRAY(String(100)))
- `journal_pgvector_001` — Migrates embeddings to pgvector Vector(1536) with HNSW index; **destructive**: purges all existing entries
- `journal_injection_tracking_001` — Adds `injection_count` (Integer) and `last_injected_at` (DateTime) columns
- `journals_stratified_001` (2026-05-05, ADR-079) — Adds `confidence`, `evidence_count`, `contradiction_count`, `level` on `journal_entries` and `journal_portrait_full`, `journal_portrait_brief`, `journal_portrait_compiled_at` on `users`. All columns nullable or with server defaults — fully reversible without data loss.
- `a92d4e713b60` — Adds rule/corpus revisions, attempt/lease columns and the evidence-event table. Existing counters are retained as historical totals; legacy `high` confidence is demoted because those totals have no independent event identities. Unversioned portraits and their provenance are cleared for lazy recompilation. Downgrade removes the new schema, but cannot restore the discarded unverifiable portrait text or prior confidence.

### Stratification (ADR-079)

Each entry carries a `level` field that captures its abstraction depth:

| Level | Role | Created by |
|---|---|---|
| **L0** | Raw observation, pre-directive — open phrasing, ephemeral | Extraction (rare, when material is too ambiguous to formulate a directive) |
| **L1** | Operational directive — `WHEN [context] → DO [action] (BECAUSE [evidence])` | Extraction (default) |
| **L2** | Transversal pattern — synthesis of multiple convergent L1 directives | **Consolidation only** (active grouping by underlying topic) |
| **L3** | Portrait facet — traits, current phase, contexts, contradictions, blind spots, evolution | **Consolidation only** (alimentation du portrait) |

The default at extraction is L1. L0 is rare. Conversational extraction cannot create L2/L3. A consolidation that creates or materially revises an L2/L3 synthesis must provide `support_ids` for multiple distinct current, high-confidence, uncontradicted L1/L2 entries with distinct complete propositions. Those supports must survive every batch mutation unchanged, including absorption as merge losers; `maintenance_actions.validate_maintenance` enforces this before embedding work. L3 belongs to `user_observations`: a method lesson cannot become an identity facet. Manual CRUD remains an explicit user control.

This is a structural precondition for synthesis, not a proof that its text follows semantically from the selected supports. New abstractions do not yet persist links to each support's proposition version: there is no complete synthesis-dependency graph for automatic downstream revalidation. The merge event/provenance ledger preserves admitted event identities, origin references and descriptive totals, but that ledger does not establish such abstraction edges. Semantic convergence and the effect of later support changes therefore remain separate evaluation and maintenance concerns.

### Epistemic status (ADR-079)

`confidence` ∈ {low, medium, high} classifies a hypothesis, provisional rule or validated rule. The model proposes confidence, while `evidence.clamp_confidence` enforces the current-version evidence bar for L0/L1 and lowers contradicted rules. Old aggregate counters cannot satisfy that bar.

Deferred self-evaluation carries the exact previous prompt exposure map `{entry_id: revision}` even when diagnostics are disabled. An outcome needs a stable event identity and the exposed revision must still be current. Replays are idempotent; an outcome for an edited rule is refused. Content replacement advances the proposition revision, resets its evidence/contradiction totals and starts provisional confidence. A title or search-hint edit preserves the proposition version. A confirming event can preserve an already-current portrait's selected words while advancing its corpus lineage; contradiction invalidates that portrait. These SQL guarantees establish bookkeeping integrity, not the semantic correctness of a model's inferred reaction.

### Data Flow

```
Conversation
    │
    ├── response_node.py ──┬── [INJECTION] build_journal_context(query=last_message)
    │                      │   → semantic search (min_score prefilter)
    │                      │   → complete entries + exposed IDs/revisions in checkpoint state
    │                      │   → ALSO: build_journal_user_model_block(format=full|brief)
    │                      │     → <UserModelContext> appended to base prompt (ADR-079)
    │                      │   → debug data → debug panel
    │                      │
    │                      └── [EXTRACTION] extract_journal_entry_background(previous exposed IDs/revisions)
    │                          → fire-and-forget → LLM introspection
    │                          → reads PsycheState.last_appraisal (inner state section, ADR-079)
    │                          → reads previous-turn directives for deferred self-evaluation (T → T+1, ADR-079)
    │                          → human-grounded actions + idempotent revision-bound reaction events
    │                          → provider preparation then short consent-fenced SQL settlement
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
    │                                  → synthesizes natural portrait_claims in the same LLM call
    │                                  → validates exact proofs; separately reviews nonempty admitted claims under the input bound
    │                                  → atomically settles actions and the reviewed portrait
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
    └── secondary flows with ambient portrait brief (ADR-079)
        ├── react_setup_node       — <UserModelContext> SystemMessage
        ├── interests/proactive_task — interest content prompt
        ├── reminder_notification  — appended to system prompt
        ├── voice/service          — appended to voice prompt
        ├── live/setup_render      — complete block at native start/wake, direct and delegated
        ├── telephony/mandates     — owner's SELF calls only; no private block for third-party/verification
        ├── heartbeat/prompts      — appended to heartbeat prompt
        └── fallback_response      — appended to fallback prompt (sync + async)
```

### Semantic Search & Prefiltering

- **Embeddings**: configured by `JournalSettings` in `core/config/journals.py`; stored widths/indexes are declared in `journals/models.py`. The centralized message vector belongs to the memory model and is reused only when model identity, configured dimensions and retrieval task match the journal wrapper; otherwise one journal-native query embedding is computed.
- **Dual-vector strategy**: every entry has a `content` embedding (title + content) and a `keyword` embedding (search_hints only). Search picks `LEAST(dist_content, dist_keyword)` per row, bridging the gap between the assistant's introspective phrasing and the user's vocabulary.
- **Search hints**: LLM-generated keywords in user vocabulary, also embedded as a separate vector
- **Min score prefilter**: entries below the floor are discarded before reaching the model. The injection's floor is learned per account within `threshold_controller.JOURNAL_INJECTION_PERIMETER`, starting from `JOURNAL_CONTEXT_MIN_SCORE`; explicit lookup keeps the configured floor. This controller optimizes exposure frequency, not answer correctness.
- **Level routing (ADR-088)**: the operational chokepoint `build_journal_context` injects **only L1/L2 behavioural directives**. L0 (private feedstock) and L3 (carried by the compiled portrait) are excluded by default via `JOURNAL_OPERATIONAL_INJECTION_EXCLUDE_LEVELS = ["L0", "L3"]`. The repository methods (`search_by_relevance`, `get_recent_for_user`) take an optional `exclude_levels` param whose **default `None` preserves the all-levels view** — extraction and consolidation call the repository directly and still see every level.
- **Operational qualification**: semantic and recency injection both request repository `operational_only=True`, excluding low-confidence and contradicted versions. Explicit lookup retains hypotheses with metadata for deliberate inspection.
- **Temporal continuity**: optional `JOURNAL_CONTEXT_RECENT_ENTRIES` bypasses the similarity floor, while retaining the same level/confidence/contradiction guards. The default disables this route; see `core/constants.py`.
- **Whole-entry budget**: the full rendered header, separators and entry metadata count within `journal_context_max_chars`. An oversized entry is omitted whole and later shorter entries may still fit; zero admitted entries produce no journal block. The rendered entry carries confidence and revision. ReAct deliberately retains its count-only, whole-entry path.
- **Injection tracking**: admitted entries increment `injection_count` and update `last_injected_at` through non-blocking `track_injected_entries`, shared with lookup. These are exposure signals, not evidence events or a causal usefulness score.
- **Dual injection**: Journal context is injected into both the **planner** (via `intelligence.original_query`) and the **response** (via `last_user_message`) prompts. Since ADR-088 the **ReAct reasoning loop** also receives L1/L2 directives, injected once at `react_setup` (count-capped by `JOURNAL_REACT_CONTEXT_MAX_ENTRIES`, full entries, no truncation) — closing the cross-mode gap. Deferred self-evaluation stays anchored to `response_node`.
- **LLM autonomy**: The LLM receives remaining entries WITH their similarity scores and decides which to use based on contextual relevance

### The journal as a lookup (ADR-318)

The injection ranks the journal on the person's MESSAGE, so a subject the turn
discovers on the way — a project named in an e-mail just read, « what did you
notice about my week » — reaches no entry. `search_journal_tool` (domain
`journal`, agent `journal_agent`, registered where `JOURNALS_ENABLED`, both
execution modes and the phone) looks such a subject up through ONE door,
`journals/search.py`:

- the subject is embedded with the JOURNAL's own model (`get_journal_embeddings`,
  the one its entries were indexed with), truncated like a user message, BEFORE
  any session opens (ADR-304); no vector means « could not look », never
  « nothing matched »;
- L0 feedstock is excluded (`JOURNAL_LOOKUP_EXCLUDE_LEVELS`): a lookup reads what
  LIA concluded — directives, patterns, portrait facets (`kind` in the answer) —
  never its unripe observations;
- the floor is the CONFIGURED `JOURNAL_CONTEXT_MIN_SCORE`, never the floor the
  controller learns for the injection, and the lookup never feeds that
  controller: the controller throttles per-message injection toward a target
  rate, a different question. Measured on 17 real entries (2026-09-25): the
  learned 0.70 kept one of the six entries scoring 0.68-0.705 for « style des
  réponses », the configured 0.63 kept them all;
- the entries returned count as injections (`track_injected_entries`) — they
  reached a prompt, which is what consolidation reads the count as.

Gated at CALL time by the capability (`PlatformCapability.JOURNALS`; the switch
also hides `journal_agent` from the planner, ADR-280) and by the person's
preference read from THEIR ROW (`journal_enabled_for`) — a voice lookup runs on a
synthetic runtime that carries no preference, and its default would read « off »
for everyone. One embedding call per lookup, recorded in the active
`TrackingContext`. At most `JOURNAL_SEARCH_MAX_RESULTS` entries, a bound stated
in the wording the planner's manifest and the ReAct schema share.

### Configuration

Defaults and bounds are owned by [`core/config/journals.py`](../../apps/api/src/core/config/journals.py), [`core/constants.py`](../../apps/api/src/core/constants.py) and the frontend API configuration. Do not copy provider or budget defaults into deployment documentation.

**System (.env)**:

- `JOURNALS_ENABLED` — Global feature flag
- `JOURNAL_EXTRACTION_ENABLED` — Post-conversation extraction
- `JOURNAL_EXTRACTION_MIN_MESSAGES` — Minimum conversation threshold
- `JOURNAL_CONSOLIDATION_INTERVAL_HOURS` / `JOURNAL_CONSOLIDATION_COOLDOWN_HOURS` — Scheduler interval and per-account attempt pacing
- `JOURNAL_CONSOLIDATION_TIMEOUT_SECONDS` — Backend timeout and lease horizon input
- `JOURNAL_CONSOLIDATION_MIN_ENTRIES` — Entry-count nomination for legacy unversioned work; corpus/source changes independently nominate accounts
- `JOURNAL_CONSOLIDATION_HISTORY_MAX_MESSAGES` / `JOURNAL_CONSOLIDATION_HISTORY_MAX_DAYS` — Optional conversation-history bounds
- `JOURNAL_DEFAULT_MAX_TOTAL_CHARS` / `JOURNAL_DEFAULT_CONTEXT_MAX_CHARS` / `JOURNAL_MAX_ENTRY_CHARS` — Default corpus, context and complete-entry ceilings
- `JOURNAL_CONTEXT_MAX_RESULTS` — Default semantic result count
- `JOURNAL_REACT_CONTEXT_MAX_ENTRIES` — ReAct and heartbeat semantic count cap; ReAct preserves full entries without a character cut — ADR-088
- `JOURNAL_CONTEXT_MIN_SCORE` — Injection starting point and explicit lookup floor — ADR-318
- `JOURNAL_SEARCH_MAX_RESULTS` — Explicit lookup result ceiling
- `JOURNAL_PORTRAIT_FULL_MAX_TOKENS` / `JOURNAL_PORTRAIT_BRIEF_MAX_TOKENS` — Enforced complete-passage compilation budgets using the application's offline OpenAI token proxy; this is not a supplier billing-token guarantee
- `JOURNAL_CONSOLIDATION_MEMORIES_MAX` / `…_INTERESTS_MAX` / `…_DEBRIEFS_MAX` — items each portrait source renders (habits are bounded by construction)
- `JOURNAL_CONSOLIDATION_SOURCE_ITEM_MAX_CHARS` — clamp per rendered item; `JOURNAL_CONSOLIDATION_SOURCES_MAX_CHARS` — cap over the four sections together (a section that does not fit is dropped whole and reported `unavailable`)
- `NEXT_PUBLIC_JOURNAL_CONSOLIDATION_TIMEOUT_MS` — Frontend manual-consolidation client timeout; the backend independently bounds its work

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

1. **Lever 1 — edit source entries**: standard CRUD via UI. Relevant rule changes invalidate derived words immediately; consolidation can subsequently rebuild them. The frontend refetches the portrait after accepted CRUD and settings mutations.
2. **Lever 2 — flag (🚩 "Signaler un problème")**: free-text feedback creates an L0 `user_correction` entry, then runs the same bounded consolidation with that signal visible.
3. **Lever 3 — manual recompile (🔄 "Consolider maintenant")**: bypasses the cooldown and runs the standard consolidation pass. Useful after a batch of edits or to refresh stale portraits.

The portrait itself is never directly editable. Users correct its sources or submit feedback; only verified source passages become its published text.

Raw `user_correction` entries preserve the accepted human correction whole. Their limit is the absolute correction cap (`JOURNAL_ENTRY_CONTENT_ABSOLUTE_MAX_LENGTH` in `journals/constants.py`), distinct from the user's lower generated-rule limit. Portrait feedback validates the combined highlighted excerpt and comment before writing: an oversized correction is rejected, never silently clipped. Generated extraction/maintenance content remains subject to `journal_max_entry_chars`.

### Consolidation lease, proof and settlement

Manual and scheduled work share `consolidation_lifecycle.claim_consolidation`. It takes the account lock, checks deployment/operator/account consent and claims an expiring owner lease before provider work. The snapshot records corpus revision, extraction-consent revision, source identity and capture time. An already-held lease performs no duplicate paid work.

Provider invocation and embedding preparation occur outside settlement locks. `current_snapshot` rechecks the same owner, consent and source state before model spend and immediately before writing. `consolidation_output.parse_maintenance_output` requires an explicit actions array, validates all actions and rejects malformed output, repeated operation IDs, invented reaction events and independent `portrait_full`/`portrait_brief` strings without evidence. `maintenance_actions.py` validates higher-level supports and complete equivalent merges, prepares embeddings and counts actual mutations; an unchanged update is not a change. Unknown IDs, invalid supports or a failed action reject the maintenance result; they cannot leave a partly applied journal.

The portrait retains the product contract of ADR-079 and ADR-292: a natural living synthesis from the assistant's perspective in the person's language. The full format integrates supported posture, current phase or focus, contexts, relationships as facets, known rhythm and observed tensions or open questions. The brief format expresses the core posture, focus and interaction guidance in a few dense natural sentences. Missing facets stay absent. Names, employer or family rosters, dates, interest weights, detector percentages, source labels and copied `WHEN -> DO` directives do not become the visible portrait. Provenance is shown separately.

The generation returns `portrait_claims` containing `facet`, natural `text`, internal `supports` and `in_brief`. The prompt offers an opaque `item_id` beside each eligible passage; a support selects that ID and its source. The server resolves the ID against the same snapshot to the complete canonical passage. Journal IDs bind the entry UUID, revision and content, and only operational confidence/contradiction-qualified entries receive them. External source sections omit items that the completeness check cannot admit. Legacy exact `quote` supports remain readable; supplying both shapes is refused. Journal supports must remain unchanged by the batch: created, updated, deleted and merged entries, including merge winners and absorbed sources, cannot self-support that run's portrait. Truncated source items and foreign or absent sources are refused. These structural traces establish where the evidence came from; they do not prove that the natural text follows from it. An independent bounded verifier checks semantic entailment, scope, style and certainty before publication. A single email-control instruction can support a bounded interaction preference about email actions, without establishing recurrence or a permanent identity. A provisional L2/L3 inference requires the `uncertainty` facet and cautious natural prose.

`portrait_review.py` builds the proofs for budget-admitted claims and performs a separate semantic review request through the configured `journal_consolidation` slot, under the same account operation and attribution context. Repeated supporting passages are sent once in a proof registry; facets refer to their indices. The entire system-and-evidence request is measured before provider work and must fit the lower of `JOURNAL_PORTRAIT_REVIEW_MAX_INPUT_TOKENS` (owned by `journals/constants.py`) and half the effective model context. Consent, source identity and the usage limit are checked before this additional spend. The complete typed response must cover each admitted claim exactly once. Only claims approved on every criterion are published; refused claims are omitted. Each claim must preserve its own subject, conditions and scope when read alone. Selection uses the original budget-admitted order and brief eligibility: removing a claim cannot refill freed budget slots or promote other prose into the brief. There is no additional model call or application-level retry/reprompt to produce this subset. A wholly refused candidate, malformed or incomplete verdict, or truncated response produces `invalid_output`, preserving an already-current portrait and the successful watermark. A refusal is never transformed into an explicit empty proposal. Provider SDK retry bounds retain their existing configured behavior. Empty or maintenance-only proposals make no review request.

The publication receipt binds the complete reviewed candidate (`reviewed_digest`) and the approved subset (`digest`), each with its exact wording, proofs, brief membership and compiler policy. `approved_indices` refer to the budget-admitted candidate; rejected indices and failed criteria are recorded without rejected prose. Both digests and the selection are rechecked at atomic publication. An approval cannot be reused for changed claims, evidence or brief membership, or when the original candidate disappears. `journal_portrait_partially_approved` records the selection counts and refused criteria for diagnosis. An empty journal does not prevent a portrait supported by authorized external sources.

Generation and review share the operation's capture and billing attribution. Known consumption from both phases is projected even if review or settlement fails; a paid partial generation failure remains known spend. Semantic review is a second judgment by the same configured model, not a statistically independent oracle or a deterministic proof of psychological truth.

`grounded_portraits` renders admitted claim text rather than its quotes or technical labels. Full and brief budgets use the application's offline token proxy and admit complete prose claims; an oversized claim is omitted whole. The brief is a deliberate selection of essential synthesized sentences, rather than a source-list prefix. Empty claims clear obsolete derived words. Source quote checking, semantic verification and finite regression tests do not establish longitudinal learning quality by themselves.

`consolidation_settlement.settle_maintenance` applies all maintenance, the validated portrait, its provenance and the successful revision watermark in one SQL transaction. A semantic mutation clears old derived words. No-action/no-portrait output preserves existing words only when their lineage already matches the captured snapshot; unverifiable or stale words are cleared. A successful no-op still advances the successful read watermark. Failed, stale or invalid attempts update attempt status/pacing and release their own lease, but never consume the successful watermark.

The scheduler's query cheaply nominates corpus/source work and `consolidation_needed` confirms source identity before calling a model. Last-entry deletion remains work via the corpus revision. `journal_last_attempted_at` paces retries independently from `journal_last_consolidated_at`, while manual triggering bypasses scheduler pacing and still respects the lease, consent and timeout.

Actual maintenance mutations also set provenance `portrait_pending`, nominating a subsequent paced pass that can synthesize from those now-current rules without allowing a batch to cite its own changes. The successful watermark still consumes that batch's writes. An already-reviewed portrait grounded in unchanged evidence may remain current while the follow-up is pending. Omitting portrait claims keeps outstanding or stale-policy portrait work pending. An explicit portrait proposal, including an empty list, clears pending work when no actual maintenance remains. A cosmetic no-op neither reopens work nor erases an already-current portrait. This follow-up is a separate scheduler/manual operation, not an automatic reprompt within the original operation.

### The four portrait sources (ADR-292)

| Source | Module | Gates (read at call time) | What the prompt receives |
|---|---|---|---|
| memories | `memories/portrait_source.py` | `MEMORY_EXTRACTION_ENABLED`, capability `MEMORY`, `user.memory_enabled` | pinned then most important, over the WHOLE set, with the emotional label and the ISO date; exact total |
| interests | `interests/portrait_source.py` | `INTEREST_EXTRACTION_ENABLED`, capability `INTERESTS` | strongest first by signal balance, with subject when clustered; exact total |
| habits | `habits/portrait_source.py` | `HABITS_ENABLED`, capability `HABITS`, `user.habits_enabled` | the CONSUMABLE windows (paused/blocked excluded) and the ACTIVE recurring requests — shape, hour, usual intent, never a date |
| relation_debriefs | `relations/debrief/portrait_source.py` | `RELATION_DEBRIEF_ENABLED`, capability `RELATION_DEBRIEF`, `user.relation_debrief_enabled` | READY rows under the published injection age, newest first, headline and standing clamped, dated |

Each reader answers `used | empty | disabled | unavailable` with an exact `total`; the seam (`domains/shared/portrait_sources.py`) is claimed by the boot (`_install_portrait_sources`, `StartupCompletenessError` on a missing source). The assembler reads one source at a time and drops a section whole over the shared cap. Source item wording comes from `journal_portrait_source_lines.txt`; complete authorized passages support the natural synthesis and remain internal evidence.

The section cap counts the actual transmitted catalogue, including reference IDs.
Provenance `used` counts only eligible offered items; `omitted_incomplete` retains
the count excluded by completeness qualification through the API boundary.
Headers report the same eligible count. Ellipsis-bearing or multiline rendered
items are conservatively omitted, including genuine ellipsis punctuation; this
is a limitation of the current rendered-source contract, not a semantic judgment.
Free subject/shape fields are flattened and bounded before rendering, so they
cannot introduce extra bullet items. Compiler-policy identity changes with the
eligibility protocol as well as the natural rendering policy; previous receipts
cannot keep derived words current under a changed proof contract.

`source_state.py` records authorization gates, source budgets, row counts and canonical fingerprints of all row identities and qualified semantic fields, plus the person's language and timezone used in rendering and the portrait compiler-policy identity. Access counters, notification cooldowns, billing metadata and recompute timestamps do not invalidate unchanged evidence. Memory usage still affects SQL ranking: an ordered selected-ID query on the owning session detects a changed page without reading vectors. Habits also bind the consumed `user_habit_profiles` payload; mirror rows alone cannot describe the learned rhythm. Non-maximal edits, deletion followed by replacement, source opt-out, locale/timezone changes and a compiler-policy change therefore invalidate the old lineage. Daily material also carries the person's local day and its natural expiry setting. `lifecycle.portrait_is_current` compares that state and the corpus revision at every ambient portrait read; there is no arbitrary age TTL. An invalid portrait is omitted until successfully recompiled. A stored extractive or unversioned portrait cannot be made current by stamping new-policy provenance onto its old words. `GET /journals/portrait` publishes current text and typed provenance; unavailable sources remain distinguishable from empty ones.

An authorized source that cannot be read defers consolidation before the paid call with `sources_unavailable`; attempt pacing applies and the scheduler retries it without consuming the successful watermark. A deliberately omitted section that exceeds the shared source budget instead carries explicit provenance `reason="over_budget"`. That bounded omission may proceed, and no passage from the omitted section is available for portrait selection.

### LLM Configuration

Two slots in `LLM_DEFAULTS` and `LLM_TYPES_REGISTRY`, with effective per-instance routing in database overrides:

- `journal_extraction` — Frequent post-conversation analysis. Reads previous exposed revisions and current `PsycheState.last_appraisal`; visible human evidence must ground new notes. Static rules, output contract and analyst persona remain above `DYNAMIC_CONTEXT_MARKER`, with turn data below for the common prompt-cache layout ([ADR-309](../architecture/ADR-309-One-Prompt-Layout-For-Every-Cache-Mechanism.md)).
- `journal_consolidation` — Bounded maintenance and natural portrait-claim generation in one call, followed by an independent bounded review only for nonempty budget-admitted claims. Review adds conditional provider work, under the same slot, account operation and token/spend attribution; an empty or maintenance-only proposal needs no review call.

Both configurable in Admin > LLM Configuration (category: `background`).

### Heartbeat Integration

Personal Journals are integrated as a context source for proactive heartbeat notifications:

- **Source name**: `journals` — appears as a toggleable badge in heartbeat settings
- **Activation**: Badge is green when `journals_enabled=true`, grayed out when disabled
- **Dynamic query**: Unlike other sources fetched in parallel, journals use a **second pass** — after all other context is aggregated (calendar, weather, emails, tasks, interests), a dynamic query is built from the aggregated summary and used for semantic search
- **Gates**: heartbeat source preference, deployment flag, operator capability and journal account preference are checked before searching and before recording a consultation
- **Budget**: shared context builder under `JOURNAL_REACT_CONTEXT_MAX_ENTRIES` and the user's rendered character budget; full directives survive without a content-preview fragment
- **Prefiltering**: shared adaptive threshold, L1/L2 level routing and operational confidence/contradiction checks
- **Prompt injection**: Journal entries appear as "ASSISTANT JOURNAL ENTRIES (your own reflections)" in the heartbeat context, allowing the assistant to personalize notification tone and content
- **Portrait brief (ADR-079)**: the notification prompt receives the current compiled brief through the same guarded portrait builder as conversation/planning.

### Native Live and telephone use

`live/setup_render.py` composes the brief portrait once for each native start or wake, for both direct and delegated providers. The user's native disabled `journal` domain prevents its ambient read. The entire existing system instruction plus portrait block must fit `LiveSetupInputs.target_tokens`; otherwise the whole block is omitted.

`telephony/mandates.append_owner_portrait` adds the same complete block only to an owner's SELF override, under `telephony_self_context_max_tokens` together with the owner context. Third-party and verification calls return before reading the private portrait. Both carriers use the application token proxy, preserve complete passages and count presence only after budget admission; these regression contracts do not assert real vendor delivery or audible behavior.

### Dedup Discipline (ADR-064 → ADR-079)

The historical post-extraction merge guard (v1.12.1) has been retired. Deduplication is now handled in two places:

1. **Extraction prompt** — instructs the LLM to update an existing entry instead of creating a near-duplicate, surfacing the most recently used entries with their full IDs and metrics.
2. **Consolidation** — emits an explicit `merge` with a winner and `merge_source_ids`. Code requires equivalent complete rules, current owned revisions and a bounded transferable provenance set. Hints and current-version event identities are unioned; a shared reaction counts once, with contradiction taking precedence for a conflicting outcome. Legacy totals remain descriptive and cannot certify high confidence. A source with retired-version evidence is refused until a lossless archive exists.

Result: noise is collapsed periodically by an LLM that sees the full corpus, not opportunistically on every turn. No silent merge LLM, no orphan migrations, no `JOURNAL_DEDUP_SIMILARITY_THRESHOLD` to tune.

### Theme Selection (ADR-079, reworked in [ADR-159](../architecture/ADR-159-Journal-Theme-Reachability.md))

Both the introspection and the consolidation prompt run the **same ordered ladder**, keyed on **what the directive is ABOUT** — never on how it is grounded. Stop at the first YES:

1. My own tone, register, pace or posture → `self_reflection`
2. A signal whose meaning holds whatever the topic is → `ideas_analyses`
3. A stable trait or preference of the user → `user_observations`
4. A specific moment taught me something about the world or my method → `learnings`

Grounding is a separate axis with exactly three admissible kinds:

| Kind | Evidence | Notes |
|---|---|---|
| **(a) SAID** | a correction, an instruction, a stated preference | quotable |
| **(b) SHOWN** | the same behaviour at least **twice** | a *full* grounding, not a lesser one; two occurrences on **different subjects** is its strongest form |
| **(c) REACTED** | the user visibly reacted to something the assistant did | **one** clear reaction suffices — both sides are pointable |

`self_reflection` requires **(c) and only (c)**: no user reaction, no entry. Surface features of the messages (length, tone, punctuation, spelling) are excluded from (b) **however often they repeat** — (b) covers what the user *does*, never how their sentences look.

Classification is **never** a distribution to balance: since [ADR-088](../architecture/ADR-088-Journal-Restraint-And-Level-Routed-Injection.md) the prompts do not push the LLM toward "underrepresented" themes (that production pressure manufactured weak entries). ADR-159 removed the opposite failure instead — a taxonomy whose rules made two of the four themes *impossible to produce or to survive*. Combined with the L0/L1/L2/L3 axis (see *Stratification* above), classification has two orthogonal dimensions: **what kind of insight** (theme) and **how distilled it is** (level).

> **Trap (measured 2026-07-27, ADR-159)** — discriminating themes on the presence of a `BECAUSE` clause empties them. *Every* theme's evidence is a past moment, so the consolidation rule "a `BECAUSE` citing a past event means `learnings`" matched every well-formed `self_reflection` (6/6 rewritten in test). Reclassify by **subject**, never by grounding shape.

> **Historical trap (ADR-159)** — a no-action return before the cooldown stamp
> repeatedly paid for the same work. The current settlement consumes successful
> no-op work, and independently records/paces unsuccessful attempts; failure is
> never represented as successful consolidation.

> **Trap (ADR-159)** — "the scheduler may still process this user" has ONE
> definition, `consolidation_eligible_user_conditions()` in
> `domains/journals/repository.py`, shared by the eligibility query and the
> portrait-age gauge. A gauge measuring a population the scheduler ignores
> reports a staleness nobody can act on: one soft-deleted account pinned it high
> for good.

**Verification.** The property "the four themes stay reachable" is enforced two ways:

- `apps/api/tests/unit/domains/journals/test_theme_reachability.py` — CI guard, pure text analysis of the shipped prompts (no LLM, no DB). Checks **parity** (every theme has a heading, an illustration and a named grounding) and **non-contradiction** (no rule rewrites `self_reflection` into `learnings`).
- `apps/api/scripts/measure_journal_themes.py` — measurement instrument: 13 conversations (two positives per theme, explicit + implicit, plus **five negatives** that must stay silent), reporting per-theme recall, volume, noise rate and token cost. Renders through `apps/api/src/domains/journals/prompt_builders.py`, the runtime's own module, so it cannot drift. Use `--introspection <file>` to A/B a candidate prompt. Placed under `apps/api/scripts/` so it ships in the prod image (`Dockerfile.prod` does `COPY . .` from that context — repo-root `scripts/` does not).

```bash
docker exec lia-api-dev python scripts/measure_journal_themes.py --reps 8 --mode both
```

Run it after **any** edit to `journal_introspection_prompt.txt` or `journal_consolidation_prompt.txt`: the CI guard catches structural regressions, only the harness catches behavioural ones.

### Anti-Hallucination Guards (v1.8.1, extended in ADR-079)

LLMs may hallucinate UUIDs, proof and derived text. The write paths validate these separately:

1. **Prompt-level guidance**: Introspection and consolidation prompts include a CRITICAL instruction to copy-paste exact UUIDs from entry headers. Entry headers use `[id=UUID | ...]` format with a dedicated ID reference table for easy copy-paste.
2. **Schema and grounding**: extraction validates IDs and human evidence, refuses new L2/L3 and applies only eligible actions. Consolidation parses its entire strict output and rejects ambiguous or incomplete operations.
3. **Ownership and revisions**: unknown/foreign IDs and stale rule/source/consent snapshots cannot settle. All short journal transactions lock the account before entries. A consolidation action failure rolls back its entire result.
4. **Independent events**: outcomes need current exposed revisions and stable source-event identities. A unique event key/revision claim precedes SQL arithmetic; absolute model counter values, replayed events and legacy totals cannot certify proof.
5. **Derived text**: internal support quotes must equal complete current authorized passages. Natural claim text needs independent semantic approval. Whole-prose token budgets, source/compiler validity and the publication receipt are enforced by code, not only requested in the prompt.

Extraction prepares embeddings after closing its read session and before acquiring the final account lock. Settlement rechecks consent, proposition revisions and the resulting title/content/search-hint payload under that lock. A concurrent metadata edit can retain the proposition revision, so revision comparison alone cannot authorize reuse of a prepared vector. Each independent extraction action uses its own savepoint; provider waiting holds neither an account lock nor a database connection.

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
- **Injection**: `context_builder(include_debug=True)` → `state_update["journal_injection_debug"]` → `streaming_service` → SSE `debug_metrics` chunk → frontend. The structural `injected_revisions` map is returned independently of diagnostics and transported to the next reaction capture.
- **Extraction**: `extract_journal_entry_background()` → `_store_extraction_debug(run_id, data)` → `pop_extraction_debug(run_id)` in streaming service → SSE `debug_metrics_update` chunk → frontend `DEBUG_METRICS_UPDATE` reducer → merged into `JournalInjectionSection.tsx`

### Extraction Debug Registry

The extraction debug registry in `extraction_debug_store.py` is an in-process dict storing debug data keyed by `run_id`:

- **Write**: `_store_extraction_debug(run_id, data)` stores results with a monotonic timestamp
- **Read**: `pop_extraction_debug(run_id)` pops and returns results (single consumption)
- **TTL eviction**: the registry's declared expiry removes unconsumed results during `pop_extraction_debug()` (for example after a streaming error or with diagnostics disabled)
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
| POST | `/journals/consolidate` | Manual bounded trigger under shared lease; actions, duration and attempt `status` (lever 3) |
| GET | `/journals/portrait` | Read current full/brief text, `compiled_at` and typed source lineage; invalid lineage returns empty text |
| POST | `/journals/portrait/feedback` | Submit a correction; creates an L0 `user_correction` entry and triggers consolidation (lever 2) |

The consolidation response's `status` comes from the caller-local `ConsolidationAttempt`, independently from the action count or another invocation's shared account status. A held lease is `busy`, while outcomes include `success`, `no_op`, `stale`, `invalid_output`, `sources_unavailable`, `disabled` and `failed`. An action count of zero alone cannot distinguish those outcomes. A publication with explicit claims, including an empty selection, is `success`; omitted claims with no maintenance actions are `no_op`. The settings announcement follows that status.

Settings PATCH compares the current locked account and reports a caller-local `portrait_invalidated` boolean; GET leaves it unknown. Changed journal consent, history policy or compilation entry/corpus ceilings invalidate the portrait. Background-consolidation switches and operational search budgets preserve it; same-value updates do not advance revisions. The frontend clears a known-invalid portrait after acknowledged source writes or compilation, even if its subsequent read fails, and exposes the read error. An ordinary failed refresh and an unchanged rejected manual attempt retain previously valid cached text. A resolved feedback response already stored a correction, so its old portrait is invalidated even if later synthesis failed.

Telephone diffusion additionally requires both the owner's rich-context preference and a context-carrying SELF mandate. The shared reader rechecks the phone preference and native journal-domain permission on its freshly loaded account; third-party, verification and delegated no-context mandates never open the portrait. Dedicated journal JSON export includes stored portrait/provenance for portability; account export additionally includes the evidence-event table. A stored export is not an ambient prompt-use permission.

The settings UI checks the attempt status before announcing success: failed, invalid, stale or busy results use the existing localized failure message. Entries, costs and portrait are still refetched after a returned attempt so invalidated derived state is visible. A failed portrait-feedback attempt keeps the correction text available for the user.

## Prometheus Metrics (ADR-079)

Defined in `src/infrastructure/observability/metrics_journals.py`:

| Metric | Type | Labels | Purpose |
|--------|------|--------|---------|
| `journal_entries_total` | Counter | `action`, `theme`, `source` | Lifecycle volume per theme and source (conversation/consolidation/manual/user_correction) |
| `journal_extraction_duration_seconds` | Histogram | `outcome` | Latency of post-conversation extraction by outcome (success/parse_failed/error) |
| `journal_zero_injection_age_days` | Gauge | — | Average age of active entries never exposed; coverage signal, not answer quality |
| `journal_evidence_total` | Counter | `outcome` | Deferred self-evaluation: `evidence` vs `contradiction` |
| `journal_consolidation_promotions_total` | Counter | `from_level`, `to_level` | Level transitions (L0↔L1, L1↔L2, L2↔L3) applied at consolidation |
| `journal_level_distribution` | Gauge | `level` | Active entries per level — sampled periodically |
| `journal_consolidation_deletes_total` | Counter | — | Committed deletions and absorbed merge sources |
| `journal_theme_distribution` | Gauge | `theme` | Active corpus by theme, including zero-count themes |
| `journal_confidence_clamped_total` | Counter | `source` | Confidence demotions when current-version proof is insufficient |
| `journal_self_eval_total` | Counter | `stage` | Exposure-to-reaction capture funnel; compare signaled versus actually applied events |
| `journal_portrait_compile_duration_seconds` | Histogram | — | Cost of in-prompt portrait compilation |
| `journal_portrait_present_total` | Counter | `flow`, `format` | Admitted portrait blocks by caller, including Live and SELF telephone carriers |
| `journal_portrait_age_hours` | Gauge | — | Oldest compiled portrait age among consolidation-eligible users; staleness diagnostic, not the read-time validity predicate |
| `journal_portrait_feedback_total` | Counter | `outcome` | Lever-2 feedback events (success/error) |
| `journal_portrait_sources_total` | Counter | `source`, `status` | What each portrait source answered at consolidation (used/empty/disabled/unavailable) — ADR-292 |

These metrics establish activity, exposure, lineage and bookkeeping. They do not establish that a selected directive was relevant or that a portrait improved an answer. Representative replay sets and human judgments must separately measure groundedness, appropriate silence, contradiction handling, selection quality and end-user behavior. Offline unit/SQL tests validate deterministic contracts; real model and native vendor qualification are separate evidence.

## Related ADRs

- [ADR-057: Personal Journals](../architecture/ADR-057-Personal-Journals.md) — Original feature
- [ADR-064: Journal Analyst Persona](../architecture/ADR-064-Journal-Analyst-Persona.md) — Persona and dedup discipline
- [ADR-069: Gemini Embedding Migration](../architecture/ADR-069-Gemini-Embedding-Migration.md) — Dual-vector search
- [ADR-079: Stratified Journal Consciousness](../architecture/ADR-079-Stratified-Journal-Consciousness.md) — Levels, epistemic status, deferred self-evaluation, portrait diffusion
- [ADR-088: Journal Restraint + Level-Routed Injection](../architecture/ADR-088-Journal-Restraint-And-Level-Routed-Injection.md) — Restraint-first write discipline, L1/L2-only operational injection, ReAct directive coherence
- [ADR-318: Exact answers, and LIA's own records, as tools](../architecture/ADR-318-Assistant-Tools-Exact-Answers-And-Own-Records.md) — The journal as a lookup (`search_journal_tool`), on the configured floor

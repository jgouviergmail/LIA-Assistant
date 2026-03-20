# ADR-057: Personal Journals (Carnets de Bord)

**Status**: ✅ IMPLEMENTED (2026-03-19)
**Author**: Claude Opus 4.6

## Context

LIA already provides user memories (psychological profile via LangGraph Store), interests tracking (PostgreSQL), and a personality system (14 profiles). However, the assistant lacks an **introspective, evolving dimension** — it does not develop its own perspective over time.

## Decision

Implement **Personal Journals** (Carnets de Bord) — thematic notebooks where the AI assistant records its own reflections, observations, analyses, and learnings. These notes are:
- Written from the assistant's first-person perspective
- Colored by the active personality
- Injected into response AND planner prompts via semantic relevance search
- Autonomously managed by the assistant (prompt-driven lifecycle, not hardcoded rules)

## Architecture

### Storage
- PostgreSQL with SQLAlchemy (`journal_entries` table)
- E5-small embeddings (384 dims) for semantic relevance search
- 4 themes: `self_reflection`, `user_observations`, `ideas_analyses`, `learnings`

### Dual Trigger
1. **Post-conversation extraction** (fire-and-forget): Analyzes last user message + context after each response. Pattern: `memory_extractor.py`.
2. **Periodic consolidation** (APScheduler): Reviews all entries, merges/summarizes/deletes. Pattern: `heartbeat_notification.py` (simplified — no ProactiveTaskRunner).

### Context Injection
- Two separate semantic searches per conversation turn:
  - **Planner**: query = user goal + intent → influences reasoning
  - **Response**: query = last user message → influences tone/formulation
- Results include similarity scores — the LLM decides relevance autonomously

### User Control
- All key parameters administered by the user (Settings > Features):
  - Enable/disable (data preserved when disabled)
  - Consolidation toggle + conversation history analysis (with cost warning)
  - Max total chars, context injection budget
- Full CRUD: read, create, modify, delete entries
- GDPR: export (JSON/CSV) + bulk delete

### Size Management
- Prompt-driven lifecycle: the assistant manages its own journals
- Global size constraint (configurable, default 40k chars)
- No hardcoded auto-archival — the LLM decides what to keep/summarize/delete

## Key Design Decisions

### Semantic Prefiltering
Entries are prefiltered by a configurable minimum cosine similarity score (`JOURNAL_CONTEXT_MIN_SCORE`, default 0.3) BEFORE being sent to the LLM. This eliminates noise and reduces prompt token usage. The LLM then decides final relevance among the remaining entries based on the scores provided.

### Heartbeat Integration
Journals are integrated as a context source for proactive notifications via a **second pass** pattern: after all other heartbeat context is aggregated (calendar, weather, emails, tasks, interests, memories), a dynamic query is built from the aggregated summary and used for semantic journal search. This ensures journal entries selected are specifically relevant to what the heartbeat is about to notify.

### Debug Panel
A dedicated "Personal Journals" section in the debug panel shows injection metrics (entries found/injected, chars budget, per-entry scores with visual bars). Data flows from `context_builder(include_debug=True)` through the state to the SSE `debug_metrics` chunk.

## Files

### New (22+ files)
- `apps/api/src/core/config/journals.py` — Settings module
- `apps/api/src/domains/journals/` — Domain package (models, schemas, repository, service, router, extraction_service, consolidation_service, context_builder, constants)
- `apps/api/src/infrastructure/scheduler/journal_consolidation.py` — APScheduler task
- `apps/api/src/domains/agents/prompts/v1/journal_*.txt` — 3 prompt files
- `apps/api/alembic/versions/2026_03_19_0002-add_journals_system.py` — Migration journals_001
- `apps/api/alembic/versions/2026_03_19_0003-add_journal_user_settings.py` — Migration journals_002
- `apps/web/src/hooks/useJournals.ts` — React hook
- `apps/web/src/components/settings/JournalsSettings.tsx` — Settings UI component
- `apps/web/src/components/debug/components/sections/JournalInjectionSection.tsx` — Debug panel section

### Modified (25+ files)
- Config MRO, constants, User model (13 columns), pipeline propagation (agents/api/router, service, orchestration), response_node (injection + extraction + debug), planner_node (injection), smart_planner_service (full chain), prompt templates (response + planner + multi-domain), prompt_loader (PromptName), LLM config (DEFAULTS + REGISTRY + LLMType), API routes + config endpoint, main.py (scheduler), exceptions, .env.example, i18n locales (6 × 3 sections), heartbeat (context_aggregator + schemas + router), debug panel (DebugPanel + types + sections index), MessagesState, alembic/env.py, model registry

## Consequences

- **Token cost**: Extra LLM call per conversation (small model, most return empty). Consolidation cost bounded by cooldown.
- **Prompt size**: ~400 tokens injection budget (configurable). Dual injection adds to both planner and response prompts. Prefiltered by min_score to reduce noise.
- **Storage**: Bounded by user-configurable max (default 40k chars per user).
- **Personality evolution**: The assistant develops a unique, coherent voice over time through its own reflections.
- **Proactive enrichment**: Heartbeat notifications are personalized by journal context (dynamic query from aggregated context).

## Alternatives Considered

1. **LangGraph Store** (like memories): Rejected — needs full CRUD for UI, structured metadata, better fits PostgreSQL pattern
2. **Hardcoded lifecycle rules**: Rejected — prompt-driven management gives the assistant maximum autonomy
3. **Recency-based injection**: Rejected — semantic relevance via embeddings is more pertinent
4. **No prefiltering**: Rejected — sending all entries to the LLM wastes tokens on irrelevant content. Min score threshold gives the right balance.

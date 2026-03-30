# ADR-066: Memory Storage Migration from LangGraph Store to PostgreSQL Custom

**Status**: ✅ ACCEPTED
**Date**: 2026-03-30
**Deciders**: JGO, Claude Code
**Technical Story**: Token optimization analysis revealed journal_extraction consumed excessive tokens; investigation expanded to centralizing embeddings and unifying memory/journal storage patterns.

---

## Context and Problem Statement

The memory system used LangGraph's `AsyncPostgresStore` for persistence, while journals used a custom PostgreSQL model with pgvector. This divergence caused:

1. **Redundant embedding calls**: 5 embeddings of the same user message per conversation turn (memory injection, journal injection planner, journal injection response, memory extraction dedup, journal extraction — all embedding the same text independently).
2. **No control over embedding lifecycle**: The store computed embeddings internally via `asearch()`, preventing reuse of pre-computed vectors.
3. **No trivialité filter**: Messages like "ok", "merci" triggered 3 full LLM extraction calls.
4. **Journal extraction loaded ALL entries**: ~7,500 input tokens per call, scaling linearly with journal size.
5. **Memory extraction was create-only**: No ability to update or delete outdated memories during extraction.

**Question**: Should we migrate memory storage to a custom PostgreSQL model (like journals) and centralize the embedding computation?

---

## Decision Drivers

### Must-Have:
1. Zero degradation of existing memory and journal functionality
2. Unified storage pattern (PostgreSQL + pgvector for both memory and journal)
3. Pre-computed embedding reuse across all consumers
4. Trivialité filter to skip extraction on trivial messages

### Nice-to-Have:
1. Memory extraction with create/update/delete (micro-consolidation)
2. Journal extraction with semantic pre-filter (reduced token usage)
3. Cross-node embedding cache (planner → response)

---

## Considered Options

### Option A: Keep LangGraph store, accept double-embed (pragmatic)
- **Pros**: Minimal changes, low risk
- **Cons**: Still 2+ embeddings per turn, no unified pattern, no trivialité filter

### Option B: Bypass store.asearch with direct SQL (hybrid)
- **Pros**: Pre-computed embedding for memory, store stays for CRUD
- **Cons**: Couples to LangGraph internal schema, maintenance burden

### Option C: Full migration to PostgreSQL custom ✅ CHOSEN
- **Pros**: Unified pattern, full embedding control, clean architecture, extensible
- **Cons**: Larger scope, data migration needed

---

## Decision

**Option C** — Full migration of memory storage from LangGraph `AsyncPostgresStore` to a dedicated SQLAlchemy `Memory` model with pgvector, aligned with the journal pattern.

### Architecture Changes:

1. **UserMessageEmbeddingService** (`src/infrastructure/llm/user_message_embedding.py`): Centralized embedding cache (text-hash keyed, TTL 5min) + trivialité filter. Computes embedding once, reused by 4 consumers.

2. **Memory model** (`src/domains/memories/models.py`): SQLAlchemy model with pgvector `Vector(1536)`, HNSW index, all existing fields preserved (content, category, emotional_weight, trigger_topic, usage_nuance, importance, usage_count, pinned, etc.).

3. **Memory repository** (`src/domains/memories/repository.py`): `search_by_relevance()` accepts pre-computed embedding vectors. Same pgvector cosine distance pattern as `JournalEntryRepository`.

4. **Memory extraction create/update/delete**: LLM can now update or delete existing memories during extraction (micro-consolidation), same pattern as journal extraction.

5. **Journal extraction semantic pre-filter**: Replaces `get_all_active()` with top-10 semantic + 3 recent entries. Reduces input tokens from ~7,500 to ~2,500.

### LangGraph Store Retention:
The `AsyncPostgresStore` remains for tool context, heartbeat context, and future documents. Only the `memories` namespace is migrated.

---

## Consequences

### Positive:
- **5→1 embedding calls** per conversation turn (centralized cache)
- **3→0 LLM extraction calls** on trivial messages (trivialité filter)
- **~67% reduction** in journal extraction input tokens (semantic pre-filter)
- **Unified pattern** between memory and journal (PostgreSQL + pgvector)
- **Memory micro-consolidation** via create/update/delete in extraction
- **Extensible**: Future features can reuse the centralized embedding service

### Negative:
- **Data migration required**: Script to copy memories from LangGraph store to new table
- **BM25 hybrid search deferred**: Feature-flagged off (pre-existing bug), semantic-only for now
- **Memory IDs change format**: `mem_<12hex>` → UUID (frontend uses opaque strings, no break)

### Neutral:
- **`updated_at` behavior change**: TimestampMixin auto-updates on PATCH (more correct than before)
- **Store stays**: Still needed for tool context — not a full removal

---

## Files Changed

### New (8):
- `src/infrastructure/llm/user_message_embedding.py`
- `src/domains/memories/models.py`
- `src/domains/memories/repository.py`
- `src/domains/memories/service.py`
- `src/domains/memories/emotional_state.py`
- `alembic/versions/2026_03_30_0001-create_memories_table.py`
- `scripts/migrate_memories_to_postgresql.py`
- `docs/architecture/ADR-066-Memory-PostgreSQL-Migration.md`

### Modified (14+):
- `src/domains/agents/middleware/memory_injection.py`
- `src/domains/agents/services/memory_extractor.py`
- `src/domains/memories/router.py`
- `src/domains/agents/nodes/response_node.py`
- `src/domains/agents/nodes/planner_node_v3.py`
- `src/domains/journals/extraction_service.py`
- `src/domains/journals/context_builder.py`
- `src/infrastructure/scheduler/memory_cleanup.py`
- And 6+ more (see plan for full list)

---

## Validation

- Unit tests: 44 test cases across 6 test files
- Integration tests: 20 test cases (API endpoints, conversation live, background systems)
- Non-regression tests: 9 end-to-end scenarios
- Linters: ruff + black + py_compile on all 23 files

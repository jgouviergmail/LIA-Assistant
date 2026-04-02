# ADR-055: RAG Spaces Architecture

**Status**: ✅ IMPLEMENTED (2026-03-14)
**Deciders**: JGO
**Technical Story**: Enable users to create personal knowledge spaces with document upload,
automatic chunking/embedding, and hybrid search (semantic + BM25) for context injection
into the AI assistant's responses.
**Related Documentation**: `docs/guides/GUIDE_RAG_SPACES.md`

> **Update v1.14.1**: Embedding model migrated from OpenAI text-embedding-3-small to Google gemini-embedding-001 (1536 dims) with RETRIEVAL task types. See [ADR-069](ADR-069-Gemini-Embedding-Migration.md).

---

## Context and Problem Statement

Users want to enrich the AI assistant's responses with their own documents (PDFs, TXT, MD, DOCX).
The system needs to:
1. Store and process uploaded documents (text extraction, chunking, embedding)
2. Perform efficient similarity search across user documents during conversations
3. Inject relevant document context into the LLM prompt
4. Track embedding costs for user billing

The existing infrastructure includes:
- `TrackedOpenAIEmbeddings` with automatic token/cost tracking
- pgvector extension (PostgreSQL) for vector similarity search
- `BM25IndexManager` for keyword-based search
- `EmbeddingTrackingContext` (ContextVar) for cost attribution
- `safe_fire_and_forget` for background tasks

## Decision Drivers

### Must-Have
- User-scoped document isolation (strict ownership enforcement)
- Hybrid search (semantic + BM25) for better retrieval quality
- Background processing (no blocking on upload)
- Cost tracking integrated with existing billing pipeline
- Feature-flagged (`rag_spaces_enabled`)

### Nice-to-Have
- Admin reindexation when embedding model changes
- Token budget hard cap to prevent context window saturation
- Multiple spaces per user with activation/deactivation

## Considered Options

### Option 1: AsyncPostgresStore (LangGraph built-in)

**Pros**: Already used for memory system, minimal new code
**Cons**: No custom `table_name` parameter — all instances share `store_vectors` table. No bulk delete SQL. Limited schema control.
**Verdict**: ❌ Rejected — insufficient schema flexibility.

> **Note (v1.14.0)**: The original dimension incompatibility between E5 (384 dims) and OpenAI (1536 dims) is no longer relevant since all subsystems now use unified embeddings. However, the dedicated table approach remains the better architectural choice for the other reasons listed.
>
> **Note (v1.14.1)**: All subsystems now use Google gemini-embedding-001 (1536 dims). The dedicated table with ALTER capability proved valuable for this migration.

### Option 2: Dedicated `rag_chunks` table with pgvector

**Pros**: Full control over schema, indexes, dimensions. Bulk delete via SQL. Standard DDD repository. No dependency on LangGraph internals. Can ALTER dimensions if embedding model changes.
**Cons**: More initial code, custom cosine similarity query.
**Verdict**: ✅ Chosen.

### Option 3: External vector database (Pinecone, Weaviate, Qdrant)

**Pros**: Managed infrastructure, horizontal scaling.
**Cons**: External dependency, latency, cost, complexity overkill for V1 scope.
**Verdict**: ❌ Rejected — unnecessary complexity.

## Decision Outcome

### Architecture Overview

```
User Upload → Service (validate + store) → Background Task
                                              ├── Extract text (PyMuPDF/python-docx)
                                              ├── Chunk (RecursiveCharacterTextSplitter)
                                              ├── Embed (TrackedOpenAIEmbeddings)
                                              └── Persist to rag_chunks (pgvector)

User Query → Response Node → retrieve_rag_context()
                               ├── Embed query (TrackedOpenAIEmbeddings)
                               ├── Cosine similarity search (pgvector)
                               ├── BM25 scoring (BM25IndexManager)
                               ├── Hybrid fusion (alpha-weighted)
                               ├── Token budget truncation (tiktoken)
                               └── Inject into system prompt
```

### Key Design Decisions

1. **Dedicated table `rag_chunks`** with `Vector(1536)` column — same dimensions as memory system (all unified on Google gemini-embedding-001 since v1.14.1)

2. **Embedding model**: Google `gemini-embedding-001` (1536 dims) — RETRIEVAL task types for optimized search (migrated from OpenAI in v1.14.1). Configurable via `rag_spaces_embedding_model`

3. **Hybrid search**: `score = α × semantic + (1-α) × BM25` with configurable alpha (default 0.7). BM25 via existing `BM25IndexManager` with per-user cache key

4. **Injection point**: Response Node only (between memory injection and knowledge enrichment). Extensible to Router/Planner in future

5. **Cost tracking**: Automatic via `TrackedOpenAIEmbeddings` + `EmbeddingTrackingContext`. Costs appear in `MessageTokenSummary`, `UserStatistics`, and assistant message bubbles

6. **Reindexation**: Admin endpoint triggers background reindex of all documents. Atomic Redis lock (`SET NX`) prevents race conditions. ALTER TABLE for dimension changes

7. **Score semantics**: Repository converts cosine distance to similarity (`1 - distance`) — callers always work with `[0, 1]` scores where higher = better

8. **EUR conversion**: Dynamic rate via `get_cached_usd_eur_rate()` (ECB/frankfurter.app, 24h Redis cache) — no hardcoded rates

### Implementation Structure (DDD)

```
src/domains/rag_spaces/
├── __init__.py
├── models.py          # RAGSpace, RAGDocument, RAGChunk (SQLAlchemy)
├── schemas.py         # Pydantic request/response schemas
├── repository.py      # RAGSpaceRepo, RAGDocumentRepo, RAGChunkRepo
├── service.py         # RAGSpaceService (CRUD + upload + delete)
├── processing.py      # Background task (extract → chunk → embed → persist)
├── retrieval.py       # Hybrid search + prompt formatting
├── embedding.py       # TrackedOpenAIEmbeddings singleton
├── reindex.py         # Admin reindexation with Redis locking
└── router.py          # FastAPI endpoints
```

### Consequences

**Positive**:
- Users can enrich AI responses with their own documents
- Full cost transparency (embedding costs tracked per document and per query)
- Feature-flagged — zero impact when disabled
- Hybrid search provides better retrieval quality than semantic-only
- Admin can safely change embedding model with full reindexation

**Negative**:
- Additional storage costs (files on disk + vectors in PostgreSQL)
- Embedding API costs for indexing and retrieval
- HNSW index maintenance overhead

**Risks**:
- Large documents (500+ chunks) could be expensive to embed — mitigated by `max_chunks_per_document` limit (configurable, default 500)
- Context window saturation — mitigated by `max_context_tokens` hard cap (default 2000 tokens)
- BM25 index memory usage — mitigated by per-user cache with TTL

**Evolution (ADR-058)**:
- `retrieve_rag_context()` now supports a `system_only=True` parameter to restrict retrieval to system spaces only (used for app-help queries)

## Validation

- [ ] Upload PDF/TXT/DOCX → document reaches `ready` status with correct chunk count
- [ ] Retrieval returns relevant chunks for queries matching document content
- [ ] Embedding costs appear in `TokenUsageLog` and `MessageTokenSummary`
- [ ] User isolation: user A cannot access user B's spaces or documents
- [ ] Feature flag: disabling `rag_spaces_enabled` removes all endpoints
- [ ] Reindexation: changing model triggers full re-embedding

## Related Decisions

- ADR-001: LangGraph Multi-Agent System (agent orchestration)
- ADR-050: Voice Domain TTS Architecture (similar background task pattern)
- ADR-053: Interest Learning System (similar DDD domain structure)
- ADR-058: System RAG Spaces — extends the RAG Spaces infrastructure with built-in system knowledge spaces (`is_system=True`) for FAQ content, App Identity Prompt injection, and `is_app_help_query()` detection
- [ADR-069: Gemini Embedding Migration](ADR-069-Gemini-Embedding-Migration.md) — Migration from OpenAI to Google gemini-embedding-001 (v1.14.1)

## References

- [pgvector documentation](https://github.com/pgvector/pgvector)
- [OpenAI Embeddings API](https://platform.openai.com/docs/guides/embeddings)
- [BM25 algorithm](https://en.wikipedia.org/wiki/Okapi_BM25)
- [Hybrid Search paper](https://arxiv.org/abs/2210.11934)

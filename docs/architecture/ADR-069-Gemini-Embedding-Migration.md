# ADR-069: Gemini Embedding Migration (OpenAI → Google)

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Date** | 2026-04-02 |
| **Supersedes** | ADR-049 (Local E5 Embeddings — archived) |
| **Related** | ADR-037 (Semantic Memory Store), ADR-066 (Memory PostgreSQL Migration) |

## Context

LIA uses embedding vectors for semantic search across four domains: memories, journals, interests, and RAG documents. The embedding model history:

1. **v1.0–v1.13.3**: `intfloat/multilingual-e5-small` (local, 384 dims) — excellent multilingual retrieval but ~1 GB RAM per worker
2. **v1.13.4**: `text-embedding-3-small` (OpenAI API, 1536 dims) — eliminated RAM overhead but introduced **language bias**: unrelated same-language texts scored 0.25–0.35 cosine similarity, while relevant matches scored only 0.29–0.48. No usable discrimination gap.
3. **v1.13.6**: Memory storage migrated from LangGraph AsyncPostgresStore (multi-vector per field) to custom PostgreSQL table (single concatenated vector). This further degraded search quality by diluting keyword signals.

The combination of model change + architecture change broke memory reference resolution ("ma femme" no longer resolved to "Hua Gouvier") and caused excessive false-positive injection of irrelevant memories.

## Decision

Migrate all embedding operations from OpenAI `text-embedding-3-small` to Google `gemini-embedding-001` with:

1. **Asymmetric task types**: `RETRIEVAL_DOCUMENT` for storage, `RETRIEVAL_QUERY` for search — aligns query and document spaces for optimal retrieval
2. **Dual-vector strategy**: Separate `embedding` (content) and `keyword_embedding` (trigger_topic / search_hints) columns, with `LEAST(dist_content, dist_keyword)` search — restores multi-field matching from the old LangGraph store
3. **Dedicated singletons per domain**: `get_memory_embeddings()`, `get_journal_embeddings()`, `get_interest_embeddings()`, `get_rag_embeddings()` — each configurable independently
4. **Dedicated Google API key**: `GOOGLE_GEMINI_API_KEY` restricted to Generative Language API, separate from the main Google API key

## Scope

| Domain | Storage | Search | Singleton |
|--------|---------|--------|-----------|
| Memories | `aembed_documents` → RETRIEVAL_DOCUMENT | `aembed_query` → RETRIEVAL_QUERY | `get_memory_embeddings()` |
| Journals | `aembed_documents` → RETRIEVAL_DOCUMENT | `aembed_query` → RETRIEVAL_QUERY | `get_journal_embeddings()` |
| Interests | `embed_documents` → RETRIEVAL_DOCUMENT | Symmetric dedup | `get_interest_embeddings()` |
| RAG Spaces | `aembed_documents` → RETRIEVAL_DOCUMENT | `aembed_query` → RETRIEVAL_QUERY | `get_rag_embeddings()` |

## Consequences

### Positive

- **Multilingual retrieval quality**: Gemini embedding-001 supports 100+ languages with proper RETRIEVAL task types, eliminating the language bias problem
- **Asymmetric query/document encoding**: Short queries match long documents effectively (equivalent to E5's "query:"/"passage:" prefixes)
- **No local model required**: API-based, no RAM overhead
- **Cost tracking**: Full Prometheus + DB billing integration via `GeminiRetrievalEmbeddings` wrapper

### Negative

- **Higher cost**: $0.15/1M tokens (Gemini) vs $0.02/1M tokens (OpenAI) — 7.5x increase per token
- **Vendor dependency**: Now depends on Google Generative Language API in addition to existing Google OAuth/Maps/Calendar APIs
- **Reindex required**: All embeddings must be recomputed on deployment (memories, journals, interests, RAG chunks)
- **Separate API key**: Requires a dedicated Google API key restricted to Generative Language API

### Migration

1. Alembic migration adds `keyword_embedding` columns to `memories` and `journal_entries`
2. `scripts/reindex_embeddings.py --only-memories` then `--only-journals` then `--skip-store --skip-memories --skip-journals` (interests)
3. RAG reindex via admin API: `POST /api/v1/rag-spaces/admin/reindex`
4. Threshold recalibration: `MEMORY_MIN_SEARCH_SCORE` may need adjustment for Gemini score distribution

## Alternatives Considered

| Alternative | Reason Rejected |
|-------------|----------------|
| Keep OpenAI text-embedding-3-small | Poor multilingual discrimination (language bias) |
| OpenAI text-embedding-3-large | Same language bias, 6.5x cost, marginal improvement |
| OpenAI text-embedding-ada-002 | Even worse discrimination (all scores 0.77–0.89) |
| Return to local E5 multilingual | ~1 GB RAM per worker, reason for original migration |
| Cohere embed-multilingual-v3 | Additional vendor dependency, less integrated with existing Google stack |
| Qwen3-Embedding-8B | Requires OpenRouter or self-hosting |

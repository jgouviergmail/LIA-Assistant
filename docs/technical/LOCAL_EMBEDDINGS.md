# Embeddings — Google Gemini gemini-embedding-001

> **Technical Documentation** - Semantic Embedding Infrastructure
>
> Version: 3.0
> Date: 2026-04-02
> Related: [ADR-069](../architecture/ADR-069-Gemini-Embedding-Migration.md) | [ADR-049](../architecture/ADR-049-Local-E5-Embeddings.md) | [SEMANTIC_ROUTER.md](SEMANTIC_ROUTER.md)

---

## Migration History

> **v1.14.1 (2026-04-02)**: Migrated from OpenAI `text-embedding-3-small` to Google `gemini-embedding-001` with asymmetric RETRIEVAL task types. OpenAI embeddings had a language bias causing poor discrimination for multilingual retrieval (unrelated same-language texts scored 0.25–0.35 cosine similarity). Gemini with `task_type=RETRIEVAL_QUERY/RETRIEVAL_DOCUMENT` provides proper query→document alignment. Added dual-vector strategy (`embedding` + `keyword_embedding`). See [ADR-069](../architecture/ADR-069-Gemini-Embedding-Migration.md).
>
> **v1.14.0 (2026-03-30)**: Replaced local E5 embeddings (`intfloat/multilingual-e5-small`, 384 dims) with OpenAI `text-embedding-3-small` (1536 dims). Removed `sentence-transformers` dependency (~1 GB RAM savings per worker).

---

## Current Model

| Property | Value |
|----------|-------|
| Provider | Google (Generative Language API) |
| Model | `gemini-embedding-001` |
| Dimensions | 1536 (configurable: 768, 1536, 3072) |
| Languages | 100+ |
| Cost | $0.15/1M tokens |
| Task Types | `RETRIEVAL_QUERY` (search), `RETRIEVAL_DOCUMENT` (storage) |
| API Key | `GOOGLE_GEMINI_API_KEY` (dedicated, restricted to Generative Language API) |

---

## Architecture

### Wrapper: GeminiRetrievalEmbeddings

`src/infrastructure/llm/gemini_embeddings.py`

Wraps `langchain_google_genai.GoogleGenerativeAIEmbeddings` to:
- Automatically inject `task_type=RETRIEVAL_QUERY` on `embed_query` / `aembed_query`
- Automatically inject `task_type=RETRIEVAL_DOCUMENT` on `embed_documents` / `aembed_documents`
- Track tokens via Prometheus metrics (reuses counters from `TrackedOpenAIEmbeddings`)
- Persist costs to DB for user billing via `EmbeddingTrackingContext`

### Domain Singletons

Each domain has its own independently configurable embedding singleton:

| Domain | Singleton | Config (`.env`) |
|--------|-----------|-----------------|
| Memories | `get_memory_embeddings()` | `MEMORY_EMBEDDING_MODEL` |
| Journals | `get_journal_embeddings()` | `JOURNAL_EMBEDDING_MODEL` |
| Interests | `get_interest_embeddings()` | `INTEREST_EMBEDDING_MODEL` |
| RAG Spaces | `get_rag_embeddings()` | `RAG_SPACES_EMBEDDING_MODEL` |

### Dual-Vector Search

Memories and journals use two embedding columns:
- `embedding`: content text only (main semantic match)
- `keyword_embedding`: trigger_topic / search_hints only (keyword-level match)

Search computes `LEAST(dist_content, COALESCE(dist_keyword, dist_content))` to pick the best match across both vectors. This restores the multi-field indexing behavior from the old LangGraph AsyncPostgresStore.

---

## Usage

All subsystems use Gemini embeddings via domain-specific singletons:

- **Semantic Memory Store** (long-term psychological profile)
- **Semantic Tool Router** (tool selection via max-pooling)
- **Interest System** (deduplication)
- **Journals** (semantic search via pgvector)
- **RAG Spaces** (document retrieval)

---

## Reindexing

After changing embedding model or dimensions:

```bash
# Memories + keywords
python scripts/reindex_embeddings.py --only-memories

# Journals + keywords  
python scripts/reindex_embeddings.py --only-journals

# Interests
python scripts/reindex_embeddings.py --skip-store --skip-memories --skip-journals

# RAG (via admin API)
curl -X POST /api/v1/rag-spaces/admin/reindex
```

---

## Related Documentation

- [ADR-069: Gemini Embedding Migration](../architecture/ADR-069-Gemini-Embedding-Migration.md)
- [ADR-049: Local E5 Embeddings](../architecture/ADR-049-Local-E5-Embeddings.md) (superseded)
- [ADR-048: Semantic Tool Router](../architecture/ADR-048-Semantic-Tool-Router.md)
- [ADR-037: Semantic Memory Store](../architecture/ADR-037-Semantic-Memory-Store.md)
- [SEMANTIC_ROUTER.md](SEMANTIC_ROUTER.md)
- [LONG_TERM_MEMORY.md](LONG_TERM_MEMORY.md)

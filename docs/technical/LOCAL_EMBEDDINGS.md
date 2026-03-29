# Embeddings — OpenAI text-embedding-3-small

> **Technical Documentation** - Semantic Embedding Infrastructure
>
> Version: 2.0
> Date: 2026-03-29
> Related: [ADR-049](../architecture/ADR-049-Local-E5-Embeddings.md) | [SEMANTIC_ROUTER.md](SEMANTIC_ROUTER.md)

---

## Migration Notice (v1.14.0)

> **Local E5 embeddings (`intfloat/multilingual-e5-small`, 384 dims) were replaced by OpenAI `text-embedding-3-small` (1536 dims) in v1.14.0.**
>
> This change unifies all embedding dimensions across the system (memory, semantic routing, interests, journals, RAG) to 1536 dims and removes the `sentence-transformers` dependency (~470MB model, ~9s startup on Raspberry Pi 5).
>
> Implementation: `apps/api/src/infrastructure/llm/memory_embeddings.py`

---

## Current Model

| Property | Value |
|----------|-------|
| Provider | OpenAI |
| Model | `text-embedding-3-small` |
| Dimensions | 1536 |
| Languages | 100+ |
| Cost | $0.02/1M tokens |

---

## Usage

All subsystems now use OpenAI embeddings via the shared embedding utility:

- **Semantic Memory Store** (long-term psychological profile)
- **Semantic Tool Router** (tool selection via max-pooling)
- **Semantic Intent Detector** (intent classification)
- **Interest System** (deduplication)
- **Journals** (semantic search via pgvector)
- **RAG Spaces** (document retrieval)

See `memory_embeddings.py` for the implementation.

---

## Related Documentation

- [ADR-049: Embeddings](../architecture/ADR-049-Local-E5-Embeddings.md) (superseded — originally local E5)
- [ADR-048: Semantic Tool Router](../architecture/ADR-048-Semantic-Tool-Router.md)
- [ADR-037: Semantic Memory Store](../architecture/ADR-037-Semantic-Memory-Store.md)
- [SEMANTIC_ROUTER.md](SEMANTIC_ROUTER.md)
- [LONG_TERM_MEMORY.md](LONG_TERM_MEMORY.md)

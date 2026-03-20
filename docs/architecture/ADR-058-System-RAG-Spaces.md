# ADR-058: System RAG Spaces for App Self-Knowledge

**Status**: Accepted
**Date**: 2026-03-19
**Deciders**: Engineering Team

## Context

LIA has a comprehensive FAQ (119+ Q&A across 17 sections) displayed in a dedicated page, but the AI assistant cannot answer questions about itself. Users asking "What can you do?" or "How do I connect my calendar?" get generic responses instead of accurate, FAQ-sourced answers.

## Decision

Implement **System RAG Spaces** — non-deletable, admin-managed knowledge spaces indexed from backend Markdown files (`docs/knowledge/*.md`). Combined with an **App Identity Prompt** and **lazy loading** triggered by `is_app_help_query` detection.

### Architecture

1. **System spaces**: `is_system=True` on `rag_spaces` table, `user_id=NULL`, partial unique indexes
2. **Content source**: 16 English Markdown files extracted from `translation.json` FAQ
3. **Indexer**: `SystemSpaceIndexer` — parse MD → embed → store chunks, SHA-256 hash-based staleness
4. **Retrieval**: Existing `retrieve_rag_context()` parameterized with `system_only=True`
5. **Detection**: `is_app_help_query` field in QueryAnalyzer → RoutingDecider Rule 0 → response node
6. **Injection**: App identity prompt + system RAG context → `{app_knowledge_context}` placeholder
7. **Admin**: 3 API endpoints + UI section with staleness badge and reindex button

### Key Decisions

- **English-only source**: LLM translates at response time (6 languages supported)
- **1 chunk = 1 Q/A pair**: Fine-grained retrieval, section metadata in JSONB
- **Lazy loading**: System RAG only retrieved when `is_app_help_query=True` (zero overhead otherwise)
- **No boost**: System results scored identically to user results
- **Atomic reindex**: Transaction rollback preserves old chunks if embedding fails
- **Separate BM25 cache**: `"rag:system"` key distinct from user `"rag:{user_id}"`

## Alternatives Considered

1. **Hardcoded system prompt**: Simple but too large (~3000 tokens for full FAQ)
2. **Frontend-only FAQ**: Already exists, but doesn't help in conversation
3. **Fine-tuning**: Expensive, not updatable without retraining

## Consequences

- Positive: Users get accurate app help directly in conversation
- Positive: Zero performance impact on normal queries (lazy loading)
- Positive: Admins can update FAQ content and reindex without deployment
- Negative: Additional embedding cost for system indexation (~119 chunks)
- Negative: Slightly larger prompt when `is_app_help_query=True` (~500 tokens)

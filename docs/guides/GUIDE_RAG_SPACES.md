# Guide RAG Spaces — LIA

> Technical and user guide for RAG Knowledge Spaces (Retrieval-Augmented Generation).

**Version**: 1.0
**Date**: 2026-03-14
**Status**: ✅ Complete
**ADR**: [ADR-055](../architecture/ADR-055-RAG-Spaces-Architecture.md)

---

## Table of Contents

- [Overview](#overview)
- [Configuration](#configuration)
- [Architecture](#architecture)
- [Document Processing Pipeline](#document-processing-pipeline)
- [Hybrid Search & Retrieval](#hybrid-search--retrieval)
- [Cost Tracking](#cost-tracking)
- [System RAG Spaces (App Self-Knowledge)](#system-rag-spaces-app-self-knowledge)
- [Admin Operations](#admin-operations)
- [API Endpoints](#api-endpoints)
- [Frontend Components](#frontend-components)
- [Observability](#observability)
- [Troubleshooting](#troubleshooting)

---

## Overview

RAG Spaces allows users to create personal knowledge spaces containing their own documents (PDF, TXT, MD, DOCX). These documents are automatically processed (text extraction, chunking, embedding) and used to enrich AI assistant responses through hybrid search (semantic + BM25).

**Key features**:
- Multiple spaces per user with activation/deactivation toggle
- Background document processing with status tracking
- Hybrid search (semantic similarity + BM25 keyword matching)
- Full cost transparency (embedding costs per document and per query)
- Admin reindexation when embedding model changes

---

## Configuration

All settings are in `src/core/config/rag_spaces.py` with defaults in `src/core/constants.py`.

| Setting | Default | Description |
|---------|---------|-------------|
| `rag_spaces_enabled` | `true` | Feature flag |
| `rag_spaces_storage_path` | `/app/data/rag_uploads` | File storage directory |
| `rag_spaces_max_file_size_mb` | `20` | Max upload size |
| `rag_spaces_max_spaces_per_user` | `10` | Max spaces per user |
| `rag_spaces_max_docs_per_space` | `50` | Max documents per space |
| `rag_spaces_max_chunks_per_document` | `500` | Max chunks per document |
| `rag_spaces_chunk_size` | `1000` | Target chunk size (chars) |
| `rag_spaces_chunk_overlap` | `200` | Overlap between chunks (chars) |
| `rag_spaces_retrieval_limit` | `5` | Max chunks per query |
| `rag_spaces_retrieval_min_score` | `0.5` | Minimum hybrid score threshold |
| `rag_spaces_max_context_tokens` | `2000` | Hard cap on RAG context tokens |
| `rag_spaces_hybrid_alpha` | `0.7` | Semantic weight (1.0 = pure semantic) |
| `rag_spaces_embedding_model` | `text-embedding-3-small` | OpenAI embedding model |
| `rag_spaces_embedding_dimensions` | `1536` | Vector dimensions |

---

## Architecture

### Domain Structure (DDD)

```
src/domains/rag_spaces/
├── models.py          # RAGSpace, RAGDocument, RAGChunk
├── schemas.py         # Pydantic API schemas
├── repository.py      # Data access (pgvector similarity search)
├── service.py         # Business logic (CRUD, upload, delete)
├── processing.py      # Background pipeline (extract → chunk → embed)
├── retrieval.py       # Hybrid search + prompt formatting
├── embedding.py       # TrackedOpenAIEmbeddings singleton
├── reindex.py         # Admin reindexation service
└── router.py          # FastAPI endpoints
```

### Database Tables

- **`rag_spaces`**: User-owned spaces with name, description, is_active toggle
- **`rag_documents`**: Uploaded documents with lifecycle status (processing/ready/error/reindexing)
- **`rag_chunks`**: Vector-indexed text chunks with pgvector `Vector(1536)` column

### File Storage

Files are stored at `{storage_path}/{user_id}/{space_id}/{uuid_filename}`.
UUID-based filenames prevent path traversal attacks.

---

## Document Processing Pipeline

When a document is uploaded:

1. **Validation**: MIME type, file extension, file size
2. **Storage**: File written to disk with UUID filename
3. **DB record**: Created with `status=processing`
4. **Background task** (via `safe_fire_and_forget`):
   - **Extract text**: PyMuPDF (PDF), python-docx (DOCX), UTF-8 read (TXT/MD)
   - **Chunk**: `RecursiveCharacterTextSplitter` with configurable size/overlap
   - **Guard**: Reject if chunk count exceeds `max_chunks_per_document`
   - **Embed**: `TrackedOpenAIEmbeddings.aembed_documents()` in batches of 100
   - **Persist**: Bulk insert `RAGChunk` objects with embeddings
   - **Update**: Document status → `ready`, store chunk count + embedding cost

**Error handling**: On failure, document status is set to `error` with a descriptive message. Embedding context is always cleared in the `finally` block.

---

## Hybrid Search & Retrieval

The `retrieve_rag_context()` function performs:

1. **Active spaces check**: Skip if no active spaces (0 cost)
2. **Reindex check**: Skip if reindexation in progress (Redis flag)
3. **Query embedding**: `TrackedOpenAIEmbeddings.aembed_query()`
4. **Semantic search**: pgvector cosine similarity (over-fetches 3x limit)
5. **BM25 scoring**: `BM25IndexManager` with per-user cache
6. **Hybrid fusion**: `score = α × semantic + (1-α) × BM25`
7. **Filtering**: Remove chunks below `min_score` threshold
8. **Truncation**: `truncate_to_token_budget()` via tiktoken
9. **Formatting**: Structured prompt context with source citations

**Score semantics**: The repository converts cosine distance to similarity (`1 - distance`), so all scores are in `[0, 1]` where higher = more relevant.

### Prompt Injection Format

```
## USER KNOWLEDGE SPACES (RAG Documents)

The following information comes from the user's personal document spaces.
Use it to enrich your response when relevant to the question.
Always cite the source document when using this information.

[Space: My Research]
Source: paper.pdf
{chunk content}
---
```

---

## Cost Tracking

Embedding costs are tracked through two parallel mechanisms:

1. **Prometheus metrics**: `embedding_tokens_consumed_total`, `embedding_cost_total` (from `TrackedOpenAIEmbeddings`)
2. **Database persistence**: `TokenUsageLog` → `MessageTokenSummary` → `UserStatistics` (via `EmbeddingTrackingContext`)

Additionally, each `RAGDocument` stores:
- `embedding_tokens`: Total tokens consumed for indexing
- `embedding_cost_eur`: Total cost in EUR (dynamic rate via `get_cached_usd_eur_rate()`)

---

## System RAG Spaces (App Self-Knowledge)

### What Are System Spaces?

System spaces are **non-deletable, admin-managed RAG spaces** that serve as the application's built-in FAQ knowledge base. Unlike user-created spaces, system spaces are owned by the platform itself and provide contextual self-knowledge — allowing LIA to answer questions about its own features, capabilities, and usage.

Key characteristics:
- **Non-deletable**: Cannot be removed through the UI or standard API calls
- **Admin-managed**: Only administrators can trigger reindexation or manage content
- **Shared knowledge**: Available to all users when relevant to their queries
- **Zero overhead**: No impact on normal conversation flow (lazy-loaded, query-gated)

### How System Spaces Work

System space content originates from Markdown knowledge files maintained in the repository:

```
docs/knowledge/*.md  →  SystemSpaceIndexer  →  pgvector chunks (rag_chunks)
```

1. **Source files**: Knowledge articles are authored as Markdown files in `docs/knowledge/`. Each file covers a specific topic (e.g., feature overview, how-to guide, FAQ entry).
2. **SystemSpaceIndexer**: At startup (or on-demand via admin endpoint), the indexer reads all knowledge files, chunks them using the same `RecursiveCharacterTextSplitter` as user documents, embeds them via `TrackedOpenAIEmbeddings`, and persists the resulting `RAGChunk` records linked to the system space.
3. **Hash-based idempotency**: Each file's content hash is stored. On subsequent runs, only changed or new files are re-indexed, making the process safe to run on every application startup.

### Query Detection and Routing

System space retrieval is triggered through a dedicated detection pipeline:

1. **`is_app_help_query` detection**: A lightweight classifier analyzes incoming messages to determine if the user is asking about LIA itself (e.g., "How do I create a space?", "What languages does LIA support?").
2. **RoutingDecider Rule 0**: When `is_app_help_query` returns `true`, the router applies Rule 0 — the highest-priority routing rule — which directs the query to the conversation node with system FAQ context injected.
3. **Response with FAQ context**: The retrieved system space chunks are formatted and injected into the prompt, allowing the LLM to answer accurately about LIA's features without hallucination.

### App Identity Prompt Injection

System space context is injected via **lazy loading** to ensure zero overhead on normal queries:

- The App Identity Prompt is **not loaded** unless `is_app_help_query` triggers
- When triggered, relevant chunks are retrieved from the system space using the same hybrid search (semantic + BM25) as user spaces
- Context is injected as a dedicated prompt section, separate from user RAG context, so the LLM can distinguish between app knowledge and user documents
- Typical latency: < 50ms for the detection step; retrieval adds standard RAG latency only when needed

### Admin Endpoints

Three dedicated admin endpoints manage system spaces:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/rag-spaces/admin/system/list` | List all system spaces with document counts and indexation status |
| `POST` | `/rag-spaces/admin/system/reindex` | Trigger re-indexation of all `docs/knowledge/*.md` files |
| `GET` | `/rag-spaces/admin/system/staleness` | Check if any knowledge files have changed since last indexation (hash comparison) |

### Admin UI

System space management is available in the frontend at **Settings > Administration > RAG Spaces**. The admin section includes:

- **System Spaces panel**: Read-only list of system spaces with document count, last indexed timestamp, and staleness indicator
- **Reindex button**: Triggers `POST /rag-spaces/admin/system/reindex` with progress feedback
- **Staleness badge**: Visual indicator (green/amber) showing whether knowledge files are up-to-date or require re-indexation

This panel is displayed alongside the existing user-space reindex controls in the `AdminRAGSpacesSection` component.

### Auto-Indexation at Startup

System spaces are automatically indexed during application startup via the `lifespan` event handler:

- **Idempotent**: Uses content hashes to skip unchanged files — safe to run on every boot
- **Non-blocking**: Runs as a background task after the application is ready to serve requests
- **Resilient**: Failures are logged but do not prevent the application from starting

### Seed Script

For initial setup or development environments, use the dedicated seed task:

```bash
task db:seed:system-rag
```

This seeds the system space record and indexes all current `docs/knowledge/*.md` files. It is idempotent and can be re-run safely.

---

## Admin Operations

### Reindexation

#### User Space Reindexation

When the admin changes `rag_spaces_embedding_model`:

1. `POST /rag-spaces/admin/reindex` triggers reindexation
2. Atomic Redis lock (`SET NX`) prevents concurrent runs
3. If dimensions change: `ALTER TABLE rag_chunks ALTER COLUMN embedding TYPE vector(N)` + recreate HNSW index
4. Each document is re-processed sequentially in background
5. `GET /rag-spaces/admin/reindex/status` polls progress

**Frontend**: The `AdminRAGSpacesSection` component shows current model, reindex button, and progress bar.

#### System Space Reindexation

System spaces can be reindexed independently of user spaces via `POST /rag-spaces/admin/system/reindex`. This re-processes all `docs/knowledge/*.md` files using the current embedding model. Unlike user reindexation, system reindex uses hash-based diffing to only re-embed changed files, making it significantly faster. Use `GET /rag-spaces/admin/system/staleness` to check whether a reindex is needed before triggering one.

---

## API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/rag-spaces` | User | List spaces with stats |
| `POST` | `/rag-spaces` | User | Create space |
| `GET` | `/rag-spaces/{id}` | User | Space detail + documents |
| `PATCH` | `/rag-spaces/{id}` | User | Update name/description |
| `DELETE` | `/rag-spaces/{id}` | User | Delete space + files |
| `PATCH` | `/rag-spaces/{id}/toggle` | User | Toggle activation |
| `POST` | `/rag-spaces/{id}/documents` | User | Upload document (multipart) |
| `DELETE` | `/rag-spaces/{id}/documents/{doc_id}` | User | Delete document |
| `GET` | `/rag-spaces/{id}/documents/{doc_id}/status` | User | Processing status |
| `POST` | `/rag-spaces/admin/reindex` | Admin | Trigger user space reindexation |
| `GET` | `/rag-spaces/admin/reindex/status` | Admin | User reindex progress |
| `GET` | `/rag-spaces/admin/system/list` | Admin | List system spaces |
| `POST` | `/rag-spaces/admin/system/reindex` | Admin | Trigger system space reindexation |
| `GET` | `/rag-spaces/admin/system/staleness` | Admin | Check system space staleness |

---

## Frontend Components

### Pages

- **`/dashboard/spaces`**: Space list with create/edit/delete + grid layout
- **`/dashboard/spaces/[id]`**: Space detail with document upload zone + document list

### Components

| Component | Purpose |
|-----------|---------|
| `SpaceCard` | Interactive card in grid (name, stats, toggle, actions) |
| `CreateSpaceDialog` | Dialog with name/description form |
| `EditSpaceDialog` | Pre-filled edit dialog |
| `DeleteSpaceConfirm` | AlertDialog confirmation |
| `DocumentUploadZone` | Drag-and-drop (desktop) / button (mobile) |
| `DocumentRow` | Document info, status badge, delete action |
| `DocumentProcessingStatus` | Status badge (processing/ready/error/reindexing) |
| `SpaceActivationToggle` | Switch toggle |
| `ActiveSpacesIndicator` | Chat header badge showing active space count |
| `SpacesSettingsSection` | Settings page section with space toggles |
| `AdminRAGSpacesSection` | Admin settings with reindex controls |

### Hooks

- `useSpaces()`: Full CRUD with optimistic updates
- `useSpaceDetail(id)`: Single space with documents
- `useActiveSpaces()`: Lightweight hook for chat indicator
- `useSpaceDocuments()`: Upload (XHR with progress), delete, status polling

---

## Observability

### Prometheus Metrics

Defined in `src/infrastructure/observability/metrics_rag_spaces.py`:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `rag_documents_processed_total` | Counter | status | Documents processed |
| `rag_document_processing_duration_seconds` | Histogram | — | Processing pipeline duration |
| `rag_document_chunks_total` | Histogram | — | Chunks per document |
| `rag_document_upload_size_bytes` | Histogram | content_type | Upload file sizes |
| `rag_retrieval_requests_total` | Counter | has_results | Retrieval requests |
| `rag_retrieval_duration_seconds` | Histogram | — | Retrieval latency |
| `rag_retrieval_chunks_returned` | Histogram | — | Chunks returned per query |
| `rag_retrieval_skipped_total` | Counter | reason | Skipped retrievals |
| `rag_embedding_tokens_total` | Counter | operation | RAG embedding tokens |
| `rag_spaces_active_count` | Gauge | — | Current active spaces |
| `rag_spaces_total_count` | Gauge | — | Total spaces |
| `rag_documents_total_count` | Gauge | status | Total documents by status |
| `rag_reindex_runs_total` | Counter | status | Reindex runs |
| `rag_reindex_documents_total` | Counter | status | Documents reindexed |

### Grafana Dashboard

Dashboard **18 - RAG Spaces / Knowledge Documents** (`18-rag-spaces.json`) with sections:
- **Overview**: Active spaces, processed docs, success rate, retrieval requests, tokens
- **Document Processing Pipeline**: Rate, duration percentiles, chunk distribution, upload sizes
- **Retrieval Performance**: Request rate, latency percentiles, chunks returned, skip reasons
- **Embedding Costs**: Token consumption by operation, API latency, cost in USD
- **Reindexation**: Run history, document success/failure

### Structured Logging

Key log events: `rag_document_processing_started`, `rag_document_processing_complete`,
`rag_retrieval_complete`, `rag_reindexation_started`, `rag_reindexation_complete`.

### Debug Panel

`rag_injection_debug` in response state includes:
- `spaces_searched`: Number of active spaces queried
- `chunks_found`: Total results above threshold
- `chunks_injected`: Final chunks after truncation
- `chunks`: Array of `{space, file, score}` per chunk

---

## Troubleshooting

### Document stuck in "processing"

1. Check logs for `rag_document_processing_failed`
2. Verify file exists at expected path
3. Check OpenAI API key is valid and has embedding permissions
4. Check `rag_spaces_max_chunks_per_document` — large documents may exceed limit

### Retrieval returns no results

1. Verify space is **active** (`is_active = true`)
2. Check documents are in **ready** status (not processing/error)
3. Lower `rag_spaces_retrieval_min_score` (default 0.5 may be too strict)
4. Check Redis for `rag_reindex_in_progress` flag
5. Verify embedding model matches between indexed chunks and query

### High embedding costs

1. Review `rag_document_chunks_total` histogram — large documents produce many chunks
2. Consider increasing `rag_spaces_chunk_size` to reduce chunk count
3. Set `rag_spaces_max_chunks_per_document` lower to reject oversized documents
4. Monitor `rag_embedding_tokens_total` by operation (index)

### Reindexation fails

1. Check Redis connectivity
2. Look for `rag_reindex_document_failed` in logs
3. Verify files still exist on disk (manual deletion breaks reindex)
4. Clear stuck Redis flag: `DEL rag_reindex_in_progress`

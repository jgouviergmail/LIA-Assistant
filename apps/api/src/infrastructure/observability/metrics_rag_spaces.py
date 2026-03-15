"""
Prometheus metrics for the RAG Spaces domain.

Follows RED methodology (Rate, Errors, Duration) pattern
from metrics_attachments.py and metrics_voice.py.

Covers:
- Document processing pipeline (upload → chunk → embed → ready)
- Retrieval performance (semantic + BM25 hybrid search)
- Space lifecycle (create, delete, toggle)

Phase: evolution — RAG Spaces (User Knowledge Documents)
Created: 2026-03-14
"""

from prometheus_client import Counter, Gauge, Histogram

# ============================================================================
# Document Processing Metrics
# ============================================================================

rag_documents_processed_total = Counter(
    "rag_documents_processed_total",
    "Total RAG documents processed (chunking + embedding)",
    ["status"],  # status: success|error
)

rag_document_processing_duration_seconds = Histogram(
    "rag_document_processing_duration_seconds",
    "RAG document processing pipeline duration (extract → chunk → embed → persist)",
    buckets=[1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0, 300.0],
)

rag_document_chunks_total = Histogram(
    "rag_document_chunks_total",
    "Number of chunks produced per document",
    buckets=[1, 5, 10, 25, 50, 100, 200, 500],
)

rag_document_upload_size_bytes = Histogram(
    "rag_document_upload_size_bytes",
    "Size of uploaded RAG documents in bytes",
    ["content_type"],  # content_type: text/plain|application/pdf|...
    buckets=[1024, 10240, 102400, 524288, 1048576, 5242880, 10485760, 20971520],
)

# ============================================================================
# Retrieval Metrics
# ============================================================================

rag_retrieval_requests_total = Counter(
    "rag_retrieval_requests_total",
    "Total RAG retrieval requests",
    ["has_results"],  # has_results: true|false
)

rag_retrieval_duration_seconds = Histogram(
    "rag_retrieval_duration_seconds",
    "RAG retrieval duration (embed query + semantic search + BM25 + fusion)",
    buckets=[0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0],
)

rag_retrieval_chunks_returned = Histogram(
    "rag_retrieval_chunks_returned",
    "Number of chunks returned per retrieval request",
    buckets=[0, 1, 2, 3, 5, 8, 10, 15, 20],
)

rag_retrieval_skipped_total = Counter(
    "rag_retrieval_skipped_total",
    "Total RAG retrieval requests skipped (no active spaces or reindexing)",
    ["reason"],  # reason: no_active_spaces|reindex_in_progress|error
)

# ============================================================================
# Embedding Metrics (RAG-specific, complements tracked_embeddings.py)
# ============================================================================

rag_embedding_tokens_total = Counter(
    "rag_embedding_tokens_total",
    "Total tokens consumed by RAG embedding operations",
    ["operation"],  # operation: index
)

# ============================================================================
# Space Lifecycle Metrics
# ============================================================================

rag_spaces_active_count = Gauge(
    "rag_spaces_active_count",
    "Current number of active RAG spaces (across all users)",
)

rag_spaces_total_count = Gauge(
    "rag_spaces_total_count",
    "Total number of RAG spaces (across all users)",
)

rag_documents_total_count = Gauge(
    "rag_documents_total_count",
    "Total number of RAG documents (across all users)",
    ["status"],  # status: processing|ready|error|reindexing
)

# ============================================================================
# Reindex Metrics
# ============================================================================

rag_reindex_runs_total = Counter(
    "rag_reindex_runs_total",
    "Total reindexation runs triggered",
    ["status"],  # status: started|completed|failed
)

rag_reindex_documents_total = Counter(
    "rag_reindex_documents_total",
    "Total documents processed during reindexation",
    ["status"],  # status: success|error
)
